import io
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS
from validator.main_validator import PGSMetadataValidator

app = Flask(__name__)
app.config["DEBUG"] = True
# File size limit set to 4MB (average is 400-500K)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1000 * 1000

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
        metadata_validator = PGSMetadataValidator(bin_file, False)
        metadata_validator.parse_spreadsheets()
        metadata_validator.parse_publication()
        metadata_validator.parse_scores()
        score_names = list(metadata_validator.parsed_scores.keys())
        metadata_validator.parse_cohorts()
        metadata_validator.parse_performances()
        metadata_validator.parse_samples()
        metadata_validator.post_parsing_checks()
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
    if metadata_validator.report['error']:
        valid = False
        error_report = metadata_validator.report['error']
        add_report_error(public_error_report, error_report)

    if metadata_validator.report['warning']:
        warning_report = metadata_validator.report['warning']
        add_report_error(public_warning_report, warning_report)

    response = {
        "valid": valid,
        "errorMessages": public_error_report,
        "warningMessages": public_warning_report,
        "scoreNames": score_names,
    }

    return jsonify(response)
