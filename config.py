class Config:
    SECURED = False
    PUBLIC_KEY_FILE = "public.pem"
    JWT_EXPECTED_ISSUER = "gwas-deposition-app"
    JWT_EXPECTED_AUDIENCE = "pgs-deposition-api"
    # File size limit set to 4MB (average is 400-500K)
    MAX_CONTENT_LENGTH = 4 * 1000 * 1000
    DEBUG = True
