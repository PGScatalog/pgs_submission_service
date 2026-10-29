import io
import logging
import os
import uuid

from flask import request, jsonify, current_app, Blueprint

import app.services.db as db
import app.services.file_transfer as file_transfer
import app.services.metadata_validator as metadata_validator
from app.security.security import require_auth
from app.security.task_auth import require_cloud_task
from app.services.file_storage import StorageService
from app.services.task_queue.task_queue import TaskQueue

bp = Blueprint("metadata", __name__)
logger = logging.getLogger(__name__)


WORKER_PATH = '/task/process_metadata'


def add_report_error(deposition_report: dict, report: dict):
    for spreadsheet in report:
        errors = []
        if spreadsheet not in deposition_report.keys():
            deposition_report[spreadsheet] = []
        for message in report[spreadsheet]:
            formatted_message = ''
            if report[spreadsheet][message][0]:
                formatted_message += "(Lines: {}) ".format(report[spreadsheet][message][0])
            formatted_message += message
            errors.append(formatted_message)
        deposition_report[spreadsheet].extend(errors)


def process_metadata(payload: dict) -> bool:
    """Returns True when finished (success OR permanent failure), False to request a retry."""
    job_id = payload.get('job_id')
    filename = payload.get('original_filename')
    storage: StorageService = current_app.extensions['storage']

    file_bytes = storage.retrieve(job_id)

    try:
        validation_results = metadata_validator.validate_metadata(io.BytesIO(file_bytes))
    except Exception as e:
        logger.exception("Task %s failed", job_id)
        db.report_metadata_validation(unique_id=job_id, report={"status": "FAILED", "error": str(e)})
        return True  # don't retry bad files

    if current_app.config.get("METADATA_FILE_TRANSFER_ENABLED", False) and validation_results.valid:
        try:
            file_transfer.upload_file_to_google_drive(file_stream=io.BytesIO(file_bytes),
                                                      file_name=filename,
                                                      unique_id=job_id)
        except Exception:
            logger.exception("Transfer failed for %s", job_id)
            return False  # retry

    valid = True
    public_error_report, public_warning_report = {}, {}
    if validation_results.error_messages:
        valid = False
        add_report_error(public_error_report, validation_results.error_messages)
    if validation_results.warning_messages:
        add_report_error(public_warning_report, validation_results.warning_messages)

    db.report_metadata_validation(
        unique_id=job_id,
        report={
            "status": "COMPLETED",
            "valid": valid,
            "errorMessages": public_error_report,
            "warningMessages": public_warning_report,
            "scoreNames": validation_results.score_names,
        }
    )
    storage.delete(job_id)
    return True


# --- 1. THE INGESTION ENDPOINT ---
@bp.route('/validate_metadata_async', methods=['POST'])
@require_auth
def validate_metadata_async():
    """Receives the file, stores it temporarily, and queues a Cloud Task."""
    if 'file' not in request.files:
        return jsonify({"error": "Missing input file"}), 400
    file = request.files['file']

    # 1. Generate a unique ID for this job
    job_id = str(uuid.uuid4())

    storage_service: StorageService = current_app.extensions['storage']
    task_queue: TaskQueue = current_app.extensions['task_queue']

    storage_service.store(file, file_name=job_id)

    db.create_metadata_validation(job_id, file.filename)

    task_queue.enqueue(
        handler=process_metadata,
        payload={"job_id": job_id, "original_filename": file.filename},
        path=WORKER_PATH,
    )

    # Return a 202 Accepted with the job ID so the frontend can poll for status
    return jsonify({
        "message": "Validation and transfer queued successfully.",
        "jobId": job_id
    }), 202


# --- 2. THE BACKGROUND WORKER ENDPOINT ---
@bp.route(WORKER_PATH, methods=['POST'])
@require_cloud_task
def process_metadata_task():
    # App Engine strips this header from external requests, so it proves the call came from Cloud Tasks.
    if os.getenv("GAE_ENV") and not request.headers.get("X-CloudTasks-QueueName"):
        return "Forbidden", 403

    payload = request.get_json()
    if not payload:
        return "Missing payload", 400

    try:
        process_metadata(payload)
    except Exception as e:
        logger.error("Exception processing")
        logger.exception(e)

    return "OK", 200


@bp.route('/validation_report/<unique_id>', methods=['GET'])
def get_validation_report(unique_id):
    validation_report = db.get_metadata_validation(unique_id)
    if not validation_report:
        return jsonify({"error": "No record with this id"}), 404

    return jsonify(validation_report)
