import pytest

from app.services.file_transfer import secure_filename


@pytest.mark.parametrize("input_filename, expected", [
    ("normal_file.csv", "normal_file.csv"),
    ("file with spaces.csv", "file_with_spaces.csv"),
    ("../../etc/passwd", "etc_passwd"),
    ("/absolute/path/file.csv", "absolute_path_file.csv"),
    ("file<script>.csv", "filescript.csv"),
    ("file\x00name.csv", "filename.csv"),  # null byte
    ("", ""),  # empty string
])
def test_secure_filename(input_filename, expected):
    assert secure_filename(input_filename) == expected
