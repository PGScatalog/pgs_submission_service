import datetime as dt
import tempfile
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import create_app
from config import Config


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


def test_missing_jwt():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/")
        assert response.status_code == 401


def test_valid_jwt(jwt_keys):
    class TestConfig(Config):
        PUBLIC_KEY_FILE = str(jwt_keys["public_key_path"])

    app = create_app(config_object=TestConfig())

    # Simulate a client signing a token with the private key
    token = encode_jwt(jwt_keys["private_key"])

    # Now, when your Flask app runs its verification logic,
    # it will read from the path in app.config['JWT_PUBLIC_KEY_PATH']
    with app.test_client() as client:
        response = client.get("/", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
