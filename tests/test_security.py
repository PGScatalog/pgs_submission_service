import datetime as dt
import tempfile
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import create_app
from app.security.security import require_auth
from config import Config

TEST_SECURED_ENDPOINT = "/secured-test"
TEST_UNSECURED_ENDPOINT = "/unsecured-test"


@pytest.fixture(scope="session")
def jwt_keys():
    """Generates an RSA key pair in memory for JWT testing."""

    # Generate the private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Serialize private key to PEM format (so PyJWT can read it)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Extract and serialize the public key to PEM format
    public_key = private_key.public_key()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Create a temporary file for the Public Key
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=True) as tmp_file:
        tmp_path = Path(tmp_file.name)
        tmp_path.write_bytes(pem_public)

        # Yield the Path object and the private key bytes
        yield {
            "private_key": pem_private,
            "public_key_path": tmp_path
        }


@pytest.fixture(scope="session")
def routes_test():
    """Defines a simple Flask Blueprint with a protected route for testing JWT authentication."""
    from flask import Blueprint, jsonify

    bp = Blueprint("test_routes", __name__)

    @bp.route(TEST_SECURED_ENDPOINT)
    @require_auth
    def protected_route():
        return jsonify({"message": "Success!"}), 200

    @bp.route(TEST_UNSECURED_ENDPOINT)
    def unprotected_route():
        return jsonify({"message": "Success!"}), 200

    return bp


def encode_jwt(private_key):
    payload = {
        "iss": "gwas-deposition-app",
        "aud": "pgs-deposition-api",
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        "iat": dt.datetime.now(dt.UTC)
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256"
    )
    return token


def test_missing_jwt(routes_test):
    app = create_app()
    app.register_blueprint(routes_test)
    with app.test_client() as client:
        response = client.get(TEST_SECURED_ENDPOINT)
        assert response.status_code == 401


def test_valid_jwt(routes_test, jwt_keys):
    class TestConfig(Config):
        PUBLIC_KEY_FILE = str(jwt_keys["public_key_path"])

    app = create_app(config_object=TestConfig())
    app.register_blueprint(routes_test)

    # Simulate a client signing a token with the private key
    token = encode_jwt(jwt_keys["private_key"])

    # Now, when your Flask app runs its verification logic,
    # it will read from the path in app.config['JWT_PUBLIC_KEY_PATH']
    with app.test_client() as client:
        response = client.get(TEST_SECURED_ENDPOINT, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200


def test_unprotected_route(routes_test):
    app = create_app()
    app.register_blueprint(routes_test)

    with app.test_client() as client:
        response = client.get(TEST_UNSECURED_ENDPOINT)
        assert response.status_code == 200
