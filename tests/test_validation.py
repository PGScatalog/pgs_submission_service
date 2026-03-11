from pathlib import Path

import pytest

VALIDATION_ENDPOINT = "/validate_metadata"
DATA_FILES_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def app():
    from app import create_app
    app = create_app(config_object="config.TestConfig")
    yield app


@pytest.fixture(scope="function")
def client(app):
    with app.test_client() as client:
        yield client


@pytest.fixture
def valid_file_path():
    return DATA_FILES_DIR / "Test_valid.xlsx"


@pytest.fixture
def invalid_file_path():
    return DATA_FILES_DIR / "Test_invalid.xlsx"


def post_template(client, file_path):
    with open(file_path, "rb") as f:
        payload = {
            "file": (f, file_path.name)
        }
        response = client.post(VALIDATION_ENDPOINT,
                               data=payload)

    assert response.status_code == 200

    return response.get_json()


def test_valid_template(client, valid_file_path):
    json_response = post_template(client, valid_file_path)
    assert json_response["valid"] is True
    assert ("errorMessages" not in json_response
            or len(json_response["errorMessages"]) == 0)


def test_invalid_template(client, invalid_file_path):
    json_response = post_template(client, invalid_file_path)
    assert json_response["valid"] is False
    assert "errorMessages" in json_response
    assert len(json_response["errorMessages"]) > 0
