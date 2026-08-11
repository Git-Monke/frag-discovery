from datetime import datetime

from pydantic import BaseModel


class GoogleLoginRequest(BaseModel):
    """The ID token a Google sign-in button produces, sent to the backend."""

    id_token: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None
    picture: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class FeedbackBody(BaseModel):
    """A taste rating on a fragrance (pass | interested | love)."""

    action: str
