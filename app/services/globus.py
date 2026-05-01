from typing import ContextManager

import logging
from pydantic import validate_call

from config import GlobusConfig
from contextlib import contextmanager
from globus_sdk import (
    TransferClient,
    AuthClient,
    GCSClient,
    GuestCollectionDocument,
    UserCredentialDocument,
    GCSAPIError, DeleteData, TransferAPIError
)
from globus_sdk.globus_app import ClientApp

logger = logging.getLogger(__name__)


class GlobusException(Exception):
    pass


class ResourceNotFoundException(GlobusException):
    pass


class MultipleResourcesFoundException(GlobusException):
    pass


class ResourceAlreadyExistsException(GlobusException):
    pass


def _get_config() -> GlobusConfig:
    from flask import current_app, has_app_context
    if has_app_context():
        return current_app.extensions["globus"]
    raise RuntimeError("No Flask app context — Globus config not initialised")


@contextmanager
def _client_app() -> ContextManager[ClientApp]:
    """Context manager for creating and cleaning up a Globus ClientApp instance."""
    config = _get_config()
    with ClientApp(
        "PGS Catalog Deposition Service",
        client_id=config.CLIENT_ID,
        client_secret=config.CLIENT_SECRET.get_secret_value(),
    ) as app:
        yield app, config


def _check_user(app, email: str) -> str | None:
    """Check if the provided email address is associated with a Globus account and return the corresponding identity ID.
    Returns None if the email address is not associated with any Globus account."""
    if email:
        with AuthClient(app=app) as auth_client:
            user_info = auth_client.get_identities(usernames=email)
            user_identity = user_info.data["identities"]
            identity_id = user_identity[0]["id"] if user_identity else None
            return identity_id
    else:
        raise ValueError("Email address is required to check user identity.")


@validate_call
def mkdir(unique_id: str, email_address: str) -> str:
    """Create a Globus guest collection on a specific directory and return the collection ID.
    This function performs the following steps:
    1. Checks if the user exists in Globus and retrieves their identity ID.
    2. Creates a directory in the mapped collection for the given unique ID.
    3. Creates a guest collection with the created directory as the base path.
    4. Adds permissions for the user to access the guest collection."""
    with _client_app() as (app, config):
        ftp_dir = config.FTP_ROOT_DIR + "/" + unique_id

        # Checking if the user exists in Globus and get their identity ID
        identity_id = _check_user(app, email_address) if email_address else None
        if not identity_id:
            raise ResourceNotFoundException("Account not linked to Globus")

        # Create the directory in the mapped collection and the FTP directory
        with TransferClient(app=app) as transfer_client:
            try:
                transfer_client.operation_mkdir(config.MAPPED_COLLECTION_ID, ftp_dir)
            except TransferAPIError as e:
                logger.error(f"Failed to create directory {ftp_dir} in mapped collection: {e}")
                if e.code == "ExternalError.MkdirFailed.Exists":
                    raise ResourceAlreadyExistsException(f"Directory {ftp_dir} already exists.")
                raise

        # Create the guest collection and add permissions for the user
        with GCSClient(config.ENDPOINT_HOSTNAME, app=app) as gcs_client:
            collection_id = _create_guest_collection(gcs_client, config, ftp_dir, unique_id)
            _add_permissions_to_endpoint(app, collection_id, identity_id)

    return collection_id


def _role_data(collection_id: str, identity: str, role: str = "administrator") -> dict:
    return {
        "DATA_TYPE": "role#1.0.0",
        "collection": collection_id,
        "principal": identity,
        "role": role,
    }


def _create_guest_collection(gcs_client: GCSClient, config: GlobusConfig, ftp_dir: str, display_name: str) -> str:

    _attach_data_access_scope(gcs_client, config.MAPPED_COLLECTION_ID)

    _ensure_user_credential(gcs_client, config)

    collection_request = GuestCollectionDocument(
        public=True,
        collection_base_path=ftp_dir,
        display_name=display_name,
        mapped_collection_id=config.MAPPED_COLLECTION_ID,
    )

    collection = gcs_client.create_collection(collection_request)
    logger.info(f"Created guest collection with ID: {collection['id']} at path: {ftp_dir}")
    collection_id = collection["id"]

    # Add roles (admin / group)
    gcs_client.create_role(
        _role_data(
            collection_id=collection_id,
            identity=f"urn:globus:auth:identity:{config.PGS_IDENTITY}",
        )
    )

    gcs_client.create_role(
        _role_data(
            collection_id=collection_id,
            identity=f"urn:globus:groups:id:{config.PGS_GLOBUS_GROUP}",
        )
    )

    logger.debug("Added administrator role for PGS Identity and group role for PGS Globus Group.")
    return collection_id


def _add_permissions_to_endpoint(app: ClientApp, collection_id: str, user_id: str) -> None:
    """Add ACL to guest collection

    Requires a transfer client call

    Arguments:
        collection_id -- collection id
        user_id -- user identity
    """
    with TransferClient(app=app) as transfer_client:
        rule_data = {
            "DATA_TYPE": "access",
            "principal_type": "identity",
            "principal": user_id,
            "path": "/",
            "permissions": "rw",
        }
        transfer_client.add_endpoint_acl_rule(collection_id, rule_data)


def _attach_data_access_scope(gcs_client: GCSClient, collection_id: str):
    """Compose and attach a "data_access" scope for the supplied collection"""
    endpoint_scopes = gcs_client.get_gcs_endpoint_scopes(gcs_client.endpoint_client_id)
    collection_scopes = gcs_client.get_gcs_collection_scopes(collection_id)

    manage_collections = endpoint_scopes.manage_collections
    data_access = collection_scopes.data_access

    gcs_client.add_app_scope(manage_collections.with_dependency(data_access))


def _ensure_user_credential(gcs_client: GCSClient, config: GlobusConfig):
    """
    Register the application's Globus Auth identity with the Storage Gateway.
    This creates a mapping between the client app's OAuth2 identity and the local \
    POSIX account on the underlying storage system, which is required before a \
    guest collection can be created. If the credential already exists, the 409 \
    response is silently ignored.
    """
    req = UserCredentialDocument(storage_gateway_id=config.STORAGE_GATEWAY_ID)
    try:
        gcs_client.create_user_credential(req)
    except GCSAPIError as err:
        # A user credential already exists, no need to create it.
        if err.http_status != 409:
            raise
        else:
            logger.debug("User credential already exists, skipping creation.")


@validate_call()
def remove_endpoint_and_delete_directory(uid) -> dict:
    """Remove the Globus endpoint associated with the given UID and delete the corresponding directory from the mapped collection."""
    logger.info(f">> remove_endpoint_and_all_contents {uid=}")
    # TODO: remove folder after deactivating endpoint, currently the folder is removed before deactivating endpoint
    #  to avoid the issue of not being able to remove folder after deactivating endpoint.
    #  This issue may be related to the delay of Globus in updating the endpoint status after deactivation,
    #  which causes the folder to be still locked for a short period of time after deactivation.
    # TODO: maybe just tag the endpoint as inactive, and have a separate process to clean up the folders of inactive endpoints.
    response = {
        "status": None
    }
    with _client_app() as (app, config):
        with TransferClient(app=app) as transfer_client:
            deactivate_status = False
            endpoint_id = _get_endpoint_id_from_uid(uid, transfer_client=transfer_client)
            logger.info(f">> remove_endpoint_and_all_contents {uid=} :: {endpoint_id=}")
            if endpoint_id:
                response['endpoint_id'] = endpoint_id
                logger.info(f">> remove_endpoint_and_all_contents {uid=} :: {endpoint_id=} true")
                if _remove_path(path_to_remove=uid, transfer_client=transfer_client, config=config):
                    with GCSClient(config.ENDPOINT_HOSTNAME, app=app) as gcs_client:
                        logger.info(f">> remove_endpoint_and_all_contents {uid=} :: remove_path true")
                        deactivate_status = _deactivate_endpoint(endpoint_id, gcs_client)
                        logger.info(f">> remove_endpoint_and_all_contents {uid=} :: {deactivate_status=}")
                        response["status"] = deactivate_status

    return response


def _get_endpoint_id_from_uid(uid: str, transfer_client: TransferClient) -> str | None:
    #search_pattern = f"-{uid[0:8]}"
    search_pattern = f"-{uid}"
    results = transfer_client.endpoint_search(search_pattern, filter_scope="shared-by-me")
    data = results.get("DATA", [])

    if not data:
        logger.warning(f"No endpoint found for UID: {uid} with search pattern: {search_pattern}")
        raise ResourceNotFoundException(f"No endpoint found for UID: {uid}")

    if len(data) > 1:
        logger.warning(f"Multiple endpoints found for UID: {uid}")
        raise MultipleResourcesFoundException(f"Multiple endpoints found for UID: {uid}")

    return data[0].get("id")


def _deactivate_endpoint(endpoint_id: str, gcs_client: GCSClient) -> int:
    logger.info(f">> deactivate_endpoint {endpoint_id=}")
    status = gcs_client.delete_collection(endpoint_id)
    logger.info(f">> deactivate_endpoint {endpoint_id=} :: {status=}")
    return status.http_status


def _remove_path(path_to_remove: str, transfer_client: TransferClient, config: GlobusConfig):
    """Deletes the given directory from the mapped collection."""
    delete_data = DeleteData(endpoint=config.MAPPED_COLLECTION_ID, recursive=True)
    delete_data.add_item(config.FTP_ROOT_DIR + '/' + path_to_remove)
    delete_result = transfer_client.submit_delete(delete_data)
    return delete_result


@validate_call()
def list_dir(unique_id: str):
    """List the contents of the directory associated with the given UID in the mapped collection."""
    with _client_app() as (app, config):
        with TransferClient(app=app) as transfer_client:
            return _dir_contents(transfer_client, config, unique_id)


def _dir_contents(transfer_client: TransferClient, config: GlobusConfig, unique_id: str) -> list | None:
    """List the contents of the directory associated with the given UID in the mapped collection.
    Only the top level of the directory is listed"""
    contents = []
    try:
        for entry in transfer_client.operation_ls(
            config.MAPPED_COLLECTION_ID, path=config.FTP_ROOT_DIR + "/" + unique_id
        ):
            contents.append(entry["name"] + ("/" if entry["type"] == "dir" else ""))
        # Note: A new operation_ls() is required for listing subdirectory contents.
    except TransferAPIError:
        return None
    return contents


def test_globus_connection():
    """Test that the Globus credentials are valid and the endpoint is reachable."""
    with _client_app() as (app, config):
        with TransferClient(app=app) as transfer_client:
            endpoint = transfer_client.get_endpoint(config.MAPPED_COLLECTION_ID)
            assert endpoint["id"] == config.MAPPED_COLLECTION_ID
            logger.info("Globus connection test successful: Endpoint is reachable and credentials are valid.")
