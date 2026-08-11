from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Google OAuth — Client ID of the "Web application" credential. Required.
    google_client_id: str

    # SQLAlchemy database URL. SQLite by default; Postgres = one-line change.
    database_url: str = "sqlite:///./data/app.db"

    # Read-only path to the fragrance catalog DB (the recommender feature
    # matrix + browse/detail reads). Copied/symlinked from frag-scraper; see
    # `make sync-catalog`. Served catalog = the recommendable pool (20+ votes,
    # 3.8+ Bayesian) plus any frag the user has seen/favorited.
    catalog_db: str = "data/fragrances.db"

    # Allowed CORS origin for the frontend (dev: Vite on :5173).
    frontend_origin: str = "http://localhost:5173"

    # Session lifetime in days.
    session_ttl_days: int = 30

    # development | production
    env: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
