from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-backed SQLite database."""
    if database_url.startswith("sqlite:///"):
        path = database_url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def _make_engine():
    settings = get_settings()
    _ensure_sqlite_dir(settings.database_url)

    kwargs: dict = {}
    if settings.database_url.startswith("sqlite"):
        # SQLite + FastAPI's threadpool: allow the connection to be shared
        # across threads. In-memory DBs need a singleton pool so the whole app
        # (and tests) share one in-process database.
        kwargs["connect_args"] = {"check_same_thread": False}
        if settings.database_url == "sqlite:///:memory:":
            kwargs["poolclass"] = StaticPool

    return create_engine(settings.database_url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency: yield a scoped session, always closed."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Create missing tables (dev bootstrap; alembic migrations come later)."""
    from app import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(engine)
