from typing import BinaryIO

import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from flask import current_app
from werkzeug.utils import secure_filename as werkzeug_secure_filename
import app.services.db as db

logger = logging.getLogger(__name__)

METADATA_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _get_credentials():
    """Load Google service account credentials from the specified JSON key file."""
    service_account_key_path = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_KEY_PATH")
    return service_account.Credentials.from_service_account_file(
        service_account_key_path,
        scopes=['https://www.googleapis.com/auth/drive']
    )


def _get_service() -> Resource:
    """Build and return a Google Drive API service object using the loaded credentials."""
    credentials = _get_credentials()
    return build('drive', 'v3', credentials=credentials)


def secure_filename(filename):
    """Sanitize the filename to prevent security issues."""
    return werkzeug_secure_filename(filename)


def _find_existing_file(service: Resource, folder_id: str, file_name: str):
    """Check if a file with the same name already exists in the destination folder."""
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    response = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = response.get("files", [])
    logger.info(f"Checked for existing file with name '{file_name}' in folder '{folder_id}'. Found {len(files)} match(es).")
    return files[0]["id"] if files else None


def upload_file_to_google_drive(file_stream: BinaryIO, file_name):
    """
    Upload a file to Google Drive, either creating a new file or updating an existing one with the same name in the
    destination folder.
    """
    file_name = secure_filename(file_name)
    dest_folder_id = current_app.config.get("GOOGLE_DRIVE_SHARED_FOLDER_ID")

    try:
        service = _get_service()

        media = MediaIoBaseUpload(file_stream, mimetype=METADATA_MIME_TYPE, resumable=True)

        existing_file_id = _find_existing_file(service, dest_folder_id, file_name)
        if existing_file_id:
            # If a file with the same name already exists, we update it instead of creating a new one,
            # keeping old versions in the GDrive file's version history.
            logger.info(f"Updating existing file with ID '{existing_file_id}'.")
            file_id = existing_file_id
            service.files().update(
                fileId=file_id,
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            ).execute()
        else:
            logger.info(f"Transferring new file with name '{file_name}'.")
            uploaded = service.files().create(
                body={
                    "name": file_name,
                    "parents": [dest_folder_id],
                },
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            ).execute()
            file_id = uploaded["id"]
        logger.info(f"File transfer complete (file ID: '{file_id}').")
        db.audit_file_transfer(file_name=file_name, success=True, error=None)

    except HttpError as e:
        logger.error(
            "Google Drive API error during upload of '%s': [%s] %s",
            file_name, e.status_code, e.error_details,
        )
        error_msg = f"Google Drive API error during upload of '{file_name}': [{e.response.status_code}] {e.response.text}"
        logger.error(error_msg, exc_info=True)
        db.audit_file_transfer(file_name=file_name, success=False, error=error_msg)
        raise

    except Exception as e:
        logger.error(
            "Unexpected error during upload of '%s': %s",
            file_name, e, exc_info=True,
        )
        error_msg = f"Unexpected error during upload of '{file_name}': {e}"
        logger.error(error_msg, exc_info=True)
        db.audit_file_transfer(file_name=file_name, success=False, error=error_msg)
        raise