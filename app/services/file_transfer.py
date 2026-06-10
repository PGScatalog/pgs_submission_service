from typing import BinaryIO
import json
import logging

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from flask import current_app
from werkzeug.utils import secure_filename as werkzeug_secure_filename
import app.services.db as db

logger = logging.getLogger(__name__)

METADATA_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"


def _get_credentials():
    """Load and refresh Google service account credentials from the specified JSON key file."""
    service_account_key_path = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_KEY_PATH")
    creds = service_account.Credentials.from_service_account_file(
        service_account_key_path,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(Request())
    return creds


def _auth_headers(creds) -> dict:
    """Return authorization headers for the given credentials."""
    return {"Authorization": f"Bearer {creds.token}"}


def secure_filename(filename):
    """Sanitize the filename to prevent security issues."""
    return werkzeug_secure_filename(filename)


def _find_existing_file(creds, folder_id: str, file_name: str):
    """Check if a file with the same name already exists in the destination folder."""
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    response = requests.get(
        f"{DRIVE_API_BASE}/files",
        headers=_auth_headers(creds),
        params={
            "q": query,
            "fields": "files(id, name)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
    )
    response.raise_for_status()
    files = response.json().get("files", [])
    logger.info(f"Checked for existing file with name '{file_name}' in folder '{folder_id}'. Found {len(files)} match(es).")
    return files[0]["id"] if files else None


def _multipart_body(metadata: dict, file_stream: BinaryIO) -> tuple[bytes, str]:
    """Build a multipart/related request body for the Drive upload."""
    boundary = "drive_upload_boundary"
    metadata_part = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
    ).encode()
    file_part = (
        f"--{boundary}\r\n"
        f"Content-Type: {METADATA_MIME_TYPE}\r\n\r\n"
    ).encode() + file_stream.read() + f"\r\n--{boundary}--".encode()

    return metadata_part + file_part, f"multipart/related; boundary={boundary}"


def _create_file(creds, folder_id: str, file_name: str, file_stream: BinaryIO) -> str:
    """Upload a new file to Google Drive and return its ID."""
    body, content_type = _multipart_body({"name": file_name, "parents": [folder_id]}, file_stream)
    response = requests.post(
        f"{DRIVE_UPLOAD_BASE}/files",
        headers={**_auth_headers(creds), "Content-Type": content_type},
        params={"uploadType": "multipart", "fields": "id,name,webViewLink", "supportsAllDrives": True},
        data=body,
    )
    response.raise_for_status()
    return response.json()["id"]


def _update_file(creds, file_id: str, file_stream: BinaryIO) -> None:
    """Update the content of an existing Google Drive file."""
    body, content_type = _multipart_body({}, file_stream)
    response = requests.patch(
        f"{DRIVE_UPLOAD_BASE}/files/{file_id}",
        headers={**_auth_headers(creds), "Content-Type": content_type},
        params={"uploadType": "multipart", "fields": "id,name,webViewLink", "supportsAllDrives": True},
        data=body,
    )
    response.raise_for_status()


def upload_file_to_google_drive(file_stream: BinaryIO, file_name: str):
    """
    Upload a file to Google Drive, either creating a new file or updating an existing one with the same name in the
    destination folder.
    """
    file_name = secure_filename(file_name)
    dest_folder_id = current_app.config.get("GOOGLE_DRIVE_SHARED_FOLDER_ID")

    try:
        creds = _get_credentials()
        existing_file_id = _find_existing_file(creds, dest_folder_id, file_name)

        if existing_file_id:
            logger.info(f"Updating existing file with ID '{existing_file_id}'.")
            _update_file(creds, existing_file_id, file_stream)
            file_id = existing_file_id
        else:
            logger.info(f"Transferring new file with name '{file_name}'.")
            file_id = _create_file(creds, dest_folder_id, file_name, file_stream)

        logger.info(f"File transfer complete (file ID: '{file_id}').")
        db.audit_file_transfer(file_name=file_name, success=True, error=None)

    except requests.HTTPError as e:
        error_msg = f"Google Drive API error during upload of '{file_name}': [{e.response.status_code}] {e.response.text}"
        logger.error(error_msg, exc_info=True)
        db.audit_file_transfer(file_name=file_name, success=False, error=error_msg)
        raise

    except Exception as e:
        error_msg = f"Unexpected error during upload of '{file_name}': {e}"
        logger.error(error_msg, exc_info=True)
        db.audit_file_transfer(file_name=file_name, success=False, error=error_msg)
        raise