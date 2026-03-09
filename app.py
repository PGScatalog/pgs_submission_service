import io
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS
import resources.metadata_validator as metadata_validator

app = Flask(__name__)
app.config.from_object("config.Config")

# CORS settings
CORS(app)
cors = CORS(app, resources={r"/": {"origins": "*"}})


@app.route("/robots.txt")
def robots_dot_txt():
    return "User-agent: *\nDisallow: /"


@app.route('/', methods=['GET'])
def home():
    return "<h1>PGS Catalog metadata validator</h1><p>This service validates the Metadata files schema and content.</p>"


def add_report_error(depositon_report: dict, report: dict):
    for spreadsheet in report:
        errors = []
        if spreadsheet not in depositon_report.keys():
            depositon_report[spreadsheet] = []
        for message in report[spreadsheet]:
            formatted_message = ''
            if report[spreadsheet][message][0]:
                formatted_message += "(Lines: {}) ".format(report[spreadsheet][message][0])
            formatted_message += message
            errors.append(formatted_message)
        depositon_report[spreadsheet].extend(errors)


@app.route('/validate_metadata', methods=['POST'])
def validate_metadata():
    file = request.files['file']

    try:
        bin_file = io.BytesIO(file.read())
        validation_results = metadata_validator.validate_metadata(bin_file)
    except Exception as e:
        logging.getLogger(__name__).error(str(e))
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
