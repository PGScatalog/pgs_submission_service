import os

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def env_bool(var_name: str, default: bool = False) -> bool:
    """Helper function to read boolean environment variables."""
    return os.environ.get(var_name, str(default)).lower() in ("true", "1", "yes")


class Config(BaseSettings):
    SECURED: bool = True
    LOCAL_PUBLIC_KEY_FILE: str = "public.pem"
    GCP_PROJECT_NAME: str | None = None
    GAE_SECRET_KEY_NAME: str | None = None
    JWT_EXPECTED_ISSUER: str = "gwas-deposition-app"
    JWT_EXPECTED_AUDIENCE: str = "pgs-deposition-api"
    # File size limit set to 4MB (average is 400-500K)
    MAX_CONTENT_LENGTH: int = 4 * 1000 * 1000
    DEBUG: bool = False

    # Database
    FIRESTORE_PROJECT_ID: str | None = None
    FIRESTORE_DATABASE_ID: str | None = None

    model_config = SettingsConfigDict(
        extra="ignore",
    )


class GlobusConfig(BaseSettings):
    MAPPED_COLLECTION_ID: str
    ENDPOINT_HOSTNAME: str
    ENDPOINT_ID: str
    STORAGE_GATEWAY_ID: str
    CLIENT_ID: str
    CLIENT_SECRET: SecretStr
    PGS_IDENTITY: str
    PGS_GLOBUS_GROUP: str
    FTP_ROOT_DIR: str

    model_config = SettingsConfigDict(
        env_prefix="GLOBUS_",
    )


class TestConfig(Config):
    SECURED: bool = False
    DEBUG: bool = True
