from os import PathLike
from typing import BinaryIO

from validator.main_validator import PGSMetadataValidator


class ValidationResults:
    def __init__(self, metadata_validator: PGSMetadataValidator, score_names: list[str]):
        self.valid = not metadata_validator.report['error']
        self.error_messages = metadata_validator.report['error']
        self.warning_messages = metadata_validator.report['warning']
        self.score_names = score_names


def validate_metadata(file: BinaryIO | str | PathLike[str]) -> ValidationResults:
    metadata_validator = PGSMetadataValidator(file, False)
    metadata_validator.parse_spreadsheets()
    metadata_validator.parse_publication()
    metadata_validator.parse_scores()
    score_names = list(metadata_validator.parsed_scores.keys())
    metadata_validator.parse_cohorts()
    metadata_validator.parse_performances()
    metadata_validator.parse_samples()
    metadata_validator.post_parsing_checks()

    return ValidationResults(metadata_validator, score_names)
