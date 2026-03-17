import os


def env_bool(var_name: str, default: bool = False) -> bool:
    """Helper function to read boolean environment variables."""
    return os.environ.get(var_name, str(default)).lower() in ("true", "1", "yes")


class Config:
    SECURED = env_bool("SECURED", default=True)
    PUBLIC_KEY_FILE = os.environ.get("PUBLIC_KEY_FILE", "public.pem")
    JWT_EXPECTED_ISSUER = os.environ.get("JWT_EXPECTED_ISSUER", "gwas-deposition-app")
    JWT_EXPECTED_AUDIENCE = os.environ.get("JWT_EXPECTED_AUDIENCE", "pgs-deposition-api")
    # File size limit set to 4MB (average is 400-500K)
    MAX_CONTENT_LENGTH = os.environ.get("MAX_CONTENT_LENGTH", 4 * 1000 * 1000)
    DEBUG = env_bool("DEBUG", default=False)


class TestConfig(Config):
    SECURED = False
    DEBUG = True
