import logging

from flask import current_app
from google.cloud import firestore

logger = logging.getLogger(__name__)
_db = None

GLOBUS_FOLDERS_COLLECTION = "globus_folders"
GLOBUS_FOLDERS_AUDIT_COLLECTION = "globus_folders_audit"


def get_db():
    """Get a Firestore client instance. Uses a global variable to ensure only one instance is created per application context."""
    global _db
    if _db is None:
        _db = firestore.Client(project=current_app.config["FIRESTORE_PROJECT_ID"], database=current_app.config["FIRESTORE_DATABASE_ID"])
    return _db


def _audit_globus_action(action: str, unique_id: str, email_address: str | None, collection_id: str | None, success: bool, error: str | None = None):
    try:
        doc = {
            "unique_id": unique_id,
            "email_address": email_address,
            "action": action,
            "success": success,
            "collection_id": collection_id,
            "error": error,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
        get_db().collection(GLOBUS_FOLDERS_AUDIT_COLLECTION).add(doc)
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
            "created_at": firestore.SERVER_TIMESTAMP,
            "disabled_at": None,
            "deleted_at": None,
        }
        # Use unique_id as document ID for easy lookup
        get_db().collection(GLOBUS_FOLDERS_COLLECTION).document(unique_id).set(doc)
    except Exception as e:
        logger.error(f"Failed to create folder record: {e}")


def disable_globus_folder(unique_id: str):
    """Mark a folder as disabled in the globus_folders collection."""
    try:
        get_db().collection(GLOBUS_FOLDERS_COLLECTION).document(unique_id).update({
            "status": "disabled",
            "disabled_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        logger.error(f"Failed to update folder status: {e}")


def delete_globus_folder(unique_id: str):
    """Mark a folder as deleted in the globus_folders collection."""
    try:
        get_db().collection(GLOBUS_FOLDERS_COLLECTION).document(unique_id).update({
            "status": "deleted",
            "deleted_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        logger.error(f"Failed to update folder status: {e}")
