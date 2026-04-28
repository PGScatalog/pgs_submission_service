from functools import wraps

import jwt
from flask import jsonify, request, g, current_app, Flask
from jwt import InvalidTokenError


def secure_app(app: Flask):
    """
    Configure the Flask app for security settings.
    """
    secured = app.config.get("SECURED", True)
    app.extensions['security'] = {
        "secured": secured,
    }
    if secured:
        app.logger.info("Security is enabled. JWT authentication will be required for protected routes.")
        try:
            with open(app.config.get("PUBLIC_KEY_FILE", "public.pem"), "r") as f:
                public_key = f.read()
        except Exception as e:
            app.logger.error(f"Failed to load public key: {e}")
            raise e

        app.extensions['security'].update({
            "public_key": public_key,
            "expected_issuer": app.config.get("JWT_EXPECTED_ISSUER"),
            "expected_audience": app.config.get("JWT_EXPECTED_AUDIENCE")
        })
    else:
        app.logger.warning("Security is disabled. JWT authentication will NOT be required for protected routes.")


def require_auth(func):
    """
    Decorator to require JWT authentication for a Flask route.
     - Checks for the presence of a Bearer token in the Authorization header.
     - Validates the token using the provided public key, expected issuer, and audience.
     - If valid, stores the decoded payload in Flask's global context (g.jwt_payload) for use in the route.
     - If invalid or missing, returns a 401 Unauthorized response with an appropriate error message.
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
            payload = jwt.decode(
                token,
                current_app.extensions['security']['public_key'],
                algorithms=["RS256"],
                audience=current_app.extensions['security']['expected_audience'],
                issuer=current_app.extensions['security']['expected_issuer'],
                options={
                    "require": ["exp", "iat"]
                }
            )

            # Store payload in Flask global context
            g.jwt_payload = payload

        except InvalidTokenError:
            return jsonify({"error": "Invalid or expired token"}), 401

        return func(*args, **kwargs)

    return wrapper
