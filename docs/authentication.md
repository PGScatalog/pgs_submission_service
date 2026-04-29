# Authentication

This API uses JWT (JSON Web Token) authentication with the following settings:

| Parameter | Value |
|-----------|-------|
| Algorithm | RS256 |
| Issuer (`iss`) | `gwas-deposition-app` |
| Audience (`aud`) | `pgs-deposition-api` |

## Prerequisites
- A `private.pem` key file
- A JWT library for your language — see [jwt.io/libraries](https://jwt.io/libraries)

## Token Requirements

Your JWT payload must include the following claims:

| Claim | Description | Example |
|-------|-------------|---------|
| `iss` | Issuer — must match exactly | `gwas-deposition-app` |
| `aud` | Audience — must match exactly | `pgs-deposition-api` |
| `iat` | Issued at (UTC timestamp) | `1714000000` |
| `exp` | Expiry (UTC timestamp) | `1714003600` |

## Using the Token

Add the token to every request as a Bearer token:

``Authorization: Bearer <your_token>``


## Example for Generating a JWT Token

### Python

```python
import jwt
from datetime import datetime, timedelta, timezone

with open("private.pem", "r") as f:
    private_key = f.read()

payload = {
    "iss": "gwas-deposition-app",
    "aud": "pgs-deposition-api",
    "iat": datetime.now(timezone.utc),
    "exp": datetime.now(timezone.utc) + timedelta(hours=1)
}

token = jwt.encode(payload, private_key, algorithm="RS256")
print(token)
```