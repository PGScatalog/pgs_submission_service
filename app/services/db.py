import logging
from datetime import datetime as dt, timezone

from flask import current_app

from app.services.document_store import DocumentStore

logger = logging.getLogger(__name__)

GLOBUS_FOLDERS_COLLECTION = "globus_folders"
GLOBUS_FOLDERS_AUDIT_COLLECTION = "globus_folders_audit"

METADATA_TRANSFER_AUDIT_COLLECTION = "metadata_transfer_audit"

METADATA_VALIDATION_COLLECTION = "metadata_validation"


def get_store() -> DocumentStore:
    """ Get the document store set during the application initialization. """
    return current_app.extensions["document_store"]


def _now():
    return dt.now(timezone.utc)


def _audit_globus_action(action: str, unique_id: str, email_address: str | None, collection_id: str | None, success: bool, error: str | None = None):
    try:
        doc = {
            "unique_id": unique_id,
            "email_address": email_address,
            "action": action,
            "success": success,
            "collection_id": collection_id,
            "error": error,
            "timestamp": _now(),
        }
        get_store().add(GLOBUS_FOLDERS_AUDIT_COLLECTION, doc)
    except Exception as e:
        # Prevent crash if audit logging fails
        logger.error(f"Failed to write audit log: {e}")


def audit_globus_mkdir(unique_id: str, success: bool, email_address: str, collection_id: str | None, error: str | None = None):
    """Write an audit entry for a Globus mkdir operation."""
    _audit_globus_action(action="mkdir", unique_id=unique_id, email_address=email_address, collection_id=collection_id,
                         success=success, error=error)


def audit_globus_disable(unique_id: str, success: bool, collection_id: str | None = None, error: str | None = None):
    """Write an audit entry for a Globus disable operation."""
    _audit_globus_action(action="disable", unique_id=unique_id, email_address=None, collection_id=collection_id,
                         success=success, error=error)


def audit_globus_delete(unique_id: str, success: bool, collection_id: str | None = None, error: str | None = None):
    """Write an audit entry for a Globus disable operation."""
    _audit_globus_action(action="delete", unique_id=unique_id, email_address=None, collection_id=collection_id,
                         success=success, error=error)


def create_globus_folder(unique_id: str, email_address: str, collection_id: str):
    """Create a folder record in the globus_folders collection."""
    try:
        doc = {
            "unique_id": unique_id,
            "email_address": email_address,
            "collection_id": collection_id,
            "status": "active",
            "created_at": _now(),
            "disabled_at": None,
            "deleted_at": None,
        }
        # Use unique_id as document ID for easy lookup
        get_store().set(GLOBUS_FOLDERS_COLLECTION, unique_id, doc)
    except Exception as e:
        logger.error(f"Failed to create folder record: {e}")


def disable_globus_folder(unique_id: str):
    """Mark a folder as disabled in the globus_folders collection."""
    try:
        get_store().update(GLOBUS_FOLDERS_COLLECTION, unique_id, {
            "status": "disabled",
            "disabled_at": _now(),
        })
    except Exception as e:
        logger.error(f"Failed to update folder status: {e}")


def delete_globus_folder(unique_id: str):
    """Mark a folder as deleted in the globus_folders collection."""
    try:
        get_store().update(GLOBUS_FOLDERS_COLLECTION, unique_id, {
            "status": "deleted",
            "disabled_at": _now(),
        })
    except Exception as e:
        logger.error(f"Failed to update folder status: {e}")


def get_endpoint_id_by_unique_id(unique_id: str) -> str | None:
    """Retrieve the Globus collection ID associated with a unique ID.
    Returns None if not found."""
    try:
        doc = get_store().get(GLOBUS_FOLDERS_COLLECTION, unique_id)
        if doc:
            return doc.get("collection_id")
        else:
            return None
    except Exception as e:
        logger.error(f"Failed to retrieve collection ID: {e}")
        return None


def audit_file_transfer(file_name: str, unique_id: str, success: bool, error: str | None = None):
    """Write an audit entry for a metadata file transfer operation."""
    try:
        doc = {
            "file_name": file_name,
            "unique_id": unique_id,
            "success": success,
            "error": error,
            "timestamp": _now(),
        }
        get_store().add(METADATA_TRANSFER_AUDIT_COLLECTION, doc)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


def create_metadata_validation(unique_id: str, filename: str | None = None):
    try:
        doc = {
            "unique_id": unique_id,
            "filename": filename,
            "status": "PENDING",
            "created_at": _now(),
            "reported_at": None,
        }
        # Use unique_id as document ID for easy lookup
        get_store().set(METADATA_VALIDATION_COLLECTION, unique_id, doc)
    except Exception as e:
        logger.error(f"Failed to create folder record: {e}")


def report_metadata_validation(unique_id: str, report: dict):
    try:
        fields = {
            "status": report.pop("status", "UNKNOWN"),
            "reported_at": _now(),
        }
        fields.update(report)
        get_store().update(METADATA_VALIDATION_COLLECTION, unique_id, fields)
    except Exception as e:
        logger.error(f"Failed to report metadata validation (id: {unique_id}): {e}")


def get_metadata_validation(unique_id: str) -> dict | None:
    try:
        return get_store().get(METADATA_VALIDATION_COLLECTION, unique_id)
    except Exception as e:
        logger.error(f"Failed to get folder record: {e}")
