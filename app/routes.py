import io
import logging

import pydantic
from flask import jsonify, request, Blueprint, make_response, abort
from pydantic import BaseModel, EmailStr, Field

import app.services.metadata_validator as metadata_validator
import app.services.globus as globus
from app import limiter

from app.security.security import require_auth
import app.services.db as db

bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)


@bp.route("/robots.txt")
@limiter.exempt
def robots_dot_txt():
    return "User-agent: *\nDisallow: /"


@bp.route('/', methods=['GET'])
@limiter.exempt
@require_auth
def home():
    return "<h1>PGS Catalog metadata validator</h1><p>This service validates the Metadata files schema and content.</p>\n"


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


@bp.route('/validate_metadata', methods=['POST'])
@require_auth
def validate_metadata():
    """Endpoint to validate metadata file. Expects a multipart/form-data request with a file field named 'file'.
    Returns a JSON response with the validation results, including whether the file is valid, any error messages, and any warning messages."""

    if 'file' not in request.files:
        return jsonify({"error": "Missing input file"}), 400
    file = request.files['file']

    try:
        bin_file = io.BytesIO(file.read())
        validation_results = metadata_validator.validate_metadata(bin_file)
    except Exception as e:
        logger.error(str(e))
        return jsonify({
            "valid": False,
            "errorMessages": {
                "Undefined": [
                    'Unexpected error in input file.'
                ]
            },
            "warningMessages": {}
        })

    valid = True
    public_error_report = {}
    public_warning_report = {}
    if validation_results.error_messages:
        valid = False
        add_report_error(public_error_report, validation_results.error_messages)

    if validation_results.warning_messages:
        add_report_error(public_warning_report, validation_results.warning_messages)

    response = {
        "valid": valid,
        "errorMessages": public_error_report,
        "warningMessages": public_warning_report,
        "scoreNames": validation_results.score_names,
    }

    return jsonify(response)


@bp.route('/globus/mkdir', methods=['POST'])
@require_auth
def globus_mkdir():
    """Endpoint to create a directory on Globus. Expects a JSON payload with 'unique_id' and 'email_address' fields.
    Returns a JSON response with the Globus collection ID if successful, or an error message if there was an issue.
    Input payload fields:
    - unique_id: A unique identifier for the directory to be created. A 409 response will be returned if a directory \
    with this ID already exists.
    - email_address: The email address of the user for whom the directory is being created. This user must be \
    with Globus, or a 404 response will be returned."""
    try:
        payload = MkdirRequest.model_validate(request.get_json())
    except pydantic.ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    try:
        collection_id = globus.mkdir(payload.unique_id, payload.email_address)
        db.create_globus_folder(unique_id=payload.unique_id, email_address=payload.email_address, collection_id=collection_id)
        db.audit_globus_mkdir(unique_id=payload.unique_id, email_address=payload.email_address,
                           collection_id=collection_id, success=True)
        return jsonify({"globusOriginID": collection_id}), 201
    except globus.ResourceAlreadyExistsException as e:
        logger.exception("Failed to create Globus directory: resource already exists")
        db.audit_globus_mkdir(unique_id=payload.unique_id, email_address=payload.email_address, collection_id=None,
                           success=False, error=str(e))
        return jsonify({"error": "Resource already exists."}), 409
    except globus.UserNotFoundException as e:
        logger.exception("Failed to create Globus directory: user not found")
        db.audit_globus_mkdir(unique_id=payload.unique_id, email_address=payload.email_address, collection_id=None,
                           success=False, error=str(e))
        return jsonify({"error": "User not found or not linked to Globus."}), 404


class MkdirRequest(BaseModel):
    """Pydantic model for validating the input payload for the /globus/mkdir endpoint."""
    unique_id: str = Field(min_length=8)
    email_address: EmailStr


@bp.route("/globus/<unique_id>", methods=["DELETE"])
@require_auth
def globus_deactivate_dir(unique_id):
    endpoint_id = None
    try:
        # Attempt to find it in DB first
        endpoint_id = db.get_endpoint_id_by_unique_id(unique_id)

        # If didn't find it in DB, attempt to find it in the mapped collection
        if not endpoint_id:
            logger.warning(f"Unique ID {unique_id} not found in DB, attempting to find in mapped collection")
            endpoint_id = globus.search_endpoint_id_from_uid(unique_id)

        if endpoint_id:
            globus.remove_endpoint(endpoint_id=endpoint_id)

            # DB logging
            db.disable_globus_folder(unique_id=unique_id)
            db.audit_globus_disable(unique_id=unique_id, collection_id=endpoint_id, success=True)

            return make_response(jsonify({"message": "Endpoint deactivated successfully."}), 200)
        else:
            raise globus.ResourceNotFoundException(f"No Globus endpoint found for unique ID {unique_id}")
    except globus.ResourceNotFoundException as e:
        logger.warning(f"No endpoint found for unique ID {unique_id}: {e}")
        return jsonify({"error": "Globus resource not found"}), 404
    except globus.MultipleResourcesFoundException as e:
        db.audit_globus_disable(unique_id=unique_id, success=False, error=str(e))
        return jsonify({"error": "Multiple matching Globus resources found."}), 409
    except Exception as e:
        logger.error(f"Failed to deactivate endpoint for unique ID {unique_id}: {e}")
        db.audit_globus_disable(
            unique_id=unique_id,
            collection_id=endpoint_id,
            success=False,
            error=str(e)
        )
        return make_response(jsonify({"error": "Failed to deactivate endpoint."}), 500)


@bp.route("/globus/<unique_id>")
@limiter.limit("10 per minute")
@require_auth
def globus_get_dir_contents(unique_id):
    resp = {"unique_id": unique_id}
    data = globus.list_dir(unique_id)
    resp["data"] = data
    if data is None:
        abort(404)
    else:
        return jsonify(resp), 200


@bp.route("/globus/test")
@limiter.limit("10 per minute")
@require_auth
def globus_test():
    globus.test_globus_connection()
    return jsonify({"message": "Globus connection successful."}), 200


@bp.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.error(f"Unexpected error: {type(e)}: {e}")
    return jsonify({"error": "An unexpected error occurred"}), 500


@bp.errorhandler(globus.ResourceNotFoundException)
def not_found(e):
    return jsonify({"error": "Globus resource not found"}), 404


@bp.errorhandler(413)
def file_too_large(e):
    return jsonify({"error": "File is too large"}), 413


@bp.errorhandler(429)
def too_many_requests(e):
    return jsonify({"error": "Too many requests, please try again later"}), 429
