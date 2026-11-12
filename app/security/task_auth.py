# app/security/task_auth.py
import functools
import logging
from flask import request, current_app, abort
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

logger = logging.getLogger(__name__)
_request = google_requests.Request()   # reuses a session and caches Google's public keys


def require_cloud_task(view):
    """Decorator that only lets requests from Cloud Tasks reach the view.

    Cloud Tasks attaches a short-lived Google-signed JWT (OIDC token) in the
    ``Authorization: Bearer <token>`` header. This decorator verifies it.

    Required config:
        BASE_URL: Public URL of this app, used to rebuild the expected audience.
        TASK_SERVICE_ACCOUNT: Email of the service account the token must be
            signed as (the same one passed to ``oidc_token`` in ``enqueue``).

    Responses:
        401: No bearer token was sent.
        403: Token is invalid, expired, has the wrong audience, or was issued
            for a different service account.
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        cfg = current_app.config

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            abort(401)

        try:
            # Verify the token. This checks, in one call:
            #    - the signature, against Google's public keys (no secret
            #      needed on our side)
            #    - the token has not expired
            #    - the issuer is Google
            #    - the audience equals the URL this route is served at, which
            #      stops a token minted for another service being replayed here.
            # It must match the "audience" set in ``oidc_token`` at enqueue
            # time. A mismatch gives a 403.
            claims = id_token.verify_oauth2_token(
                auth.removeprefix("Bearer "),
                _request,
                audience=f"{cfg['BASE_URL']}{request.path}",
            )
        except ValueError:  # bad signature, expired, wrong audience
            logger.warning("Rejected task request: invalid token")
            abort(403)

        # A valid Google token isn't enough: any Google service account
        # could get one with the right audience. Require that it was signed
        # as OUR service account.
        if (claims.get("email") != cfg["GCT_SERVICE_ACCOUNT"]
                or not claims.get("email_verified")):
            logger.warning("Rejected task request: unexpected identity %s", claims.get("email"))
            abort(403)

        return view(*args, **kwargs)
    return wrapper
