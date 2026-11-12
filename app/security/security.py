import os
from functools import wraps

import jwt
from flask import jsonify, request, g, current_app, Flask
from jwt import InvalidTokenError


def _load_public_key(app: Flask, secret_name: str | None) -> str:
    """Load one public key.
     - In production (App Engine), load the issuer's key from GCP Secret Manager.
     - In local development, load the single test key from LOCAL_PUBLIC_KEY_FILE
       (default: public.pem), regardless of the issuer."""
    if os.getenv("GAE_ENV"):  # set automatically by App Engine
        from google.cloud import secretmanager
        project_id = app.config.get("GCP_PROJECT_NAME")
        if not project_id or not secret_name:
            raise RuntimeError("Missing GCP_PROJECT_NAME or secret_name in production environment")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        return client.access_secret_version(name=name).payload.data.decode("utf-8")
    else:
        app.logger.info("Running in local environment, loading public key from file")
        key_file = app.config.get("LOCAL_PUBLIC_KEY_FILE", "public.pem")
        with open(key_file, "r") as f:
            return f.read()


def secure_app(app: Flask):
    """
    Configure the Flask app for security settings.
    Loads the public key of every whitelisted issuer once, at startup, and caches it
    in app.extensions['security']['issuers'].
    """
    secured = app.config.get("SECURED", True)
    app.extensions["security"] = {"secured": secured, "issuers": {}}

    if not secured:
        app.logger.warning("Security is disabled. JWT authentication will NOT be required for protected routes.")
        return

    issuers_cfg = app.config.get("JWT_ISSUERS") or {}
    if not issuers_cfg:
        raise RuntimeError("Security is enabled but JWT_ISSUERS is empty")

    expected_audience = app.config.get("JWT_EXPECTED_AUDIENCE")
    if not expected_audience:
        raise RuntimeError("Security is enabled but JWT_EXPECTED_AUDIENCE is not set")

    app.logger.info("Security is enabled. Loading public keys for %d issuer(s).", len(issuers_cfg))

    for issuer, cfg in issuers_cfg.items():
        try:
            public_key = _load_public_key(app, (cfg or {}).get("secret_name"))
        except Exception as e:
            app.logger.error(f"Failed to load public key for issuer '{issuer}': {e}")
            raise
        app.extensions["security"]["issuers"][issuer] = {"public_key": public_key}

    app.extensions["security"]["expected_audience"] = expected_audience


def _get_unverified_issuer(token: str) -> str | None:
    """Read 'iss' WITHOUT verifying the signature.
    The value is untrusted: it is only ever used as a lookup key into the
    whitelist of issuers loaded at startup. The token is then fully verified
    with the key found for that issuer."""
    unverified = jwt.decode(token, options={"verify_signature": False})
    iss = unverified.get("iss")
    return iss if isinstance(iss, str) else None


def require_auth(func):
    """
    Decorator to require JWT authentication for a Flask route.
     - Checks for the presence of a Bearer token in the Authorization header.
     - Looks up the public key from the (unverified) issuer, which must be in the whitelist.
     - Validates the token using that key, the issuer and the expected audience.
     - If valid, stores the decoded payload in g.jwt_payload.
     - If invalid or missing, returns a 401 Unauthorized response.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        security = current_app.extensions.get("security")

        # Check if security extension is configured (use secure_app(app))
        if not security:
            current_app.logger.error("Security extension not configured.")
            return jsonify({"error": "Server configuration error"}), 500

        if not security["secured"]:
            return func(*args, **kwargs)

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        auth_header_parts = auth_header.split(" ", 1)

        if len(auth_header_parts) != 2 or auth_header_parts[0] != "Bearer":
            return jsonify({"error": "Invalid Authorization header"}), 401

        token = auth_header_parts[1]

        # Limit CPU usage by rejecting excessively long tokens
        if len(token) > 8000:
            return jsonify({"error": "Token is too long"}), 401

        try:
            issuer = _get_unverified_issuer(token)
            issuer_cfg = security["issuers"].get(issuer) if issuer else None

            # Unknown issuer: same generic error, no hint about which issuers exist
            if issuer_cfg is None:
                return jsonify({"error": "Invalid or expired token"}), 401

            payload = jwt.decode(
                token,
                issuer_cfg["public_key"],
                algorithms=["RS256"],
                audience=security["expected_audience"],
                issuer=issuer,
                options={"require": ["exp", "iat", "iss"]},
            )

            # Store payload (and which issuer signed it) in Flask global context
            g.jwt_payload = payload
            g.jwt_issuer = issuer

        except InvalidTokenError:  # includes DecodeError for malformed tokens
            return jsonify({"error": "Invalid or expired token"}), 401

        return func(*args, **kwargs)

    return wrapper
