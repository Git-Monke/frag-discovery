"""Bearer-token session dependency + session helpers.

Sessions are opaque tokens stored only as SHA-256 hashes. The raw token is
returned to the client once at login; every later request sends it in the
`Authorization: Bearer <token>` header, and we look it up by its hash.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.db import get_db
from app.models import Session as SessionModel
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize to tz-aware UTC for compare."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: OrmSession, user_id: int) -> tuple[str, datetime]:
    """Mint a new session, persist only its hash, and return (raw, expires_at)."""
    settings = get_settings()
    raw = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(days=settings.session_ttl_days)
    db.add(
        SessionModel(
            user_id=user_id,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
    )
    db.commit()
    return raw, expires_at


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: OrmSession = Depends(get_db),
) -> tuple[User, SessionModel]:
    """Resolve the bearer token to its (user, session). Raises 401 otherwise."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session",
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    session = (
        db.query(SessionModel)
        .filter(SessionModel.token_hash == hash_token(credentials.credentials))
        .first()
    )
    if session is None or ensure_utc(session.expires_at) <= _utcnow():
        raise unauthorized

    user = db.get(User, session.user_id)
    if user is None:
        raise unauthorized

    return user, session


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: OrmSession = Depends(get_db),
) -> User | None:
    """Resolve the bearer token to its user without raising, for endpoints
    that work signed-out (e.g. /api/fragrance). Returns None when absent or
    invalid, the User otherwise."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None

    session = (
        db.query(SessionModel)
        .filter(SessionModel.token_hash == hash_token(credentials.credentials))
        .first()
    )
    if session is None or ensure_utc(session.expires_at) <= _utcnow():
        return None
    return db.get(User, session.user_id)
