import os

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def env_bool(var_name: str, default: bool = False) -> bool:
    """Helper function to read boolean environment variables."""
    return os.environ.get(var_name, str(default)).lower() in ("true", "1", "yes")


class Config(BaseSettings):
    SECURED: bool = True
    PUBLIC_KEY_FILE: str = "public.pem"
    JWT_EXPECTED_ISSUER: str = "gwas-deposition-app"
    JWT_EXPECTED_AUDIENCE: str = "pgs-deposition-api"
    # File size limit set to 4MB (average is 400-500K)
    MAX_CONTENT_LENGTH = os.environ.get("MAX_CONTENT_LENGTH", 4 * 1000 * 1000)
    DEBUG = env_bool("DEBUG", default=False)
    MAX_CONTENT_LENGTH: int = 4 * 1000 * 1000
    DEBUG: bool = False



class TestConfig(Config):
    SECURED: bool = False
    DEBUG: bool = True
