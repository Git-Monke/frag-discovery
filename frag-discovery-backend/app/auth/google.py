"""Google ID-token verification.

This is the only seam that talks to Google at login time. It verifies the
token's signature against Google's public keys (cached automatically by
google-auth) and checks the audience matches our client ID. Tests stub this
function; everything else flows from it.
"""

from dataclasses import dataclass

import google.auth.transport.requests
from google.oauth2 import id_token

from app.config import get_settings


class InvalidGoogleTokenError(Exception):
    """Raised when the ID token is malformed, expired, or fails verification."""


@dataclass(frozen=True)
class GoogleClaims:
    sub: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


def verify_google_id_token(id_token_str: str) -> GoogleClaims:
    """Verify a Google ID token and return its claims.

    Raises InvalidGoogleTokenError on any failure (bad signature, wrong
    audience, expired, unknown issuer, or unverified email).
    """
    settings = get_settings()
    try:
        info = id_token.verify_oauth2_token(
            id_token_str,
            google.auth.transport.requests.Request(),
            settings.google_client_id,
        )
    except Exception as exc:  # ValueError on bad signature/expiry, etc.
        raise InvalidGoogleTokenError("Invalid Google ID token") from exc

    if not info.get("email_verified"):
        raise InvalidGoogleTokenError("Google email is not verified")

    return GoogleClaims(
        sub=info["sub"],
        email=info["email"],
        email_verified=True,
        name=info.get("name"),
        picture=info.get("picture"),
    )
