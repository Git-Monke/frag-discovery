"""Auth routes: Google sign-in, current user, logout."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as OrmSession

from app.auth.dependencies import create_session, ensure_utc, get_current_session
from app.auth.google import InvalidGoogleTokenError, verify_google_id_token
from app.db import get_db
from app.models import Session as SessionModel
from app.models import User
from app.schemas import AuthResponse, GoogleLoginRequest, UserOut

router = APIRouter()


@router.post("/google", response_model=AuthResponse)
def google_login(
    body: GoogleLoginRequest,
    db: OrmSession = Depends(get_db),
) -> AuthResponse:
    try:
        claims = verify_google_id_token(body.id_token)
    except InvalidGoogleTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = db.query(User).filter(User.google_sub == claims.sub).first()
    if user is None:
        user = User(
            google_sub=claims.sub,
            email=claims.email,
            name=claims.name,
            picture=claims.picture,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Upsert: refresh mutable profile fields on each login.
        dirty = False
        for attr in ("email", "name", "picture"):
            if getattr(user, attr) != getattr(claims, attr):
                setattr(user, attr, getattr(claims, attr))
                dirty = True
        if dirty:
            db.commit()

    raw, expires_at = create_session(db, user.id)
    expires_in = int((ensure_utc(expires_at) - datetime.now(UTC)).total_seconds())
    return AuthResponse(
        access_token=raw,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(auth: tuple[User, SessionModel] = Depends(get_current_session)) -> User:
    user, _ = auth
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    auth: tuple[User, SessionModel] = Depends(get_current_session),
    db: OrmSession = Depends(get_db),
) -> None:
    _, session = auth
    db.delete(session)
    db.commit()
