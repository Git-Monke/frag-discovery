from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """A person who signed in with Google."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Google's stable subject identifier — the identity key for upserts.
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["UserFeedback"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """An opaque bearer-token session (token stored as a SHA-256 hash)."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class Favorite(Base):
    """A fragrance a user favorited. `frag_id` references the read-only catalog
    DB (no FK — it lives in a separate database)."""

    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "frag_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    frag_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="favorites")


class UserFeedback(Base):
    """A taste rating on a fragrance (the recommender's training signal).

    `action` is one of the 3-level scale: `pass` / `interested` / `love`.
    A `love` rating is always mirrored by a `Favorite` row (love == favorite).
    """

    __tablename__ = "user_feedback"
    __table_args__ = (UniqueConstraint("user_id", "frag_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    frag_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    weight: Mapped[float] = mapped_column(default=-1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="feedback")
