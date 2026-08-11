import os
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Deterministic settings for tests. Env vars take precedence over .env in
# pydantic-settings, and these must be set before the app modules are imported
# (get_settings() + the engine are built at import time).
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
# Tests run the sparse recommender path (no embedding .npy files needed).
os.environ["REC_EMBED_DIM"] = "0"

from app import catalog as catalog_mod
from app import recommender
from app.auth import routes
from app.auth.google import GoogleClaims
from app.catalog import Catalog
from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    """TestClient whose DB is an isolated temp-file SQLite database."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def login(client, monkeypatch):
    """Sign in a user and return Authorization headers. Call with `sub` to
    switch users (each call overrides the stubbed Google verifier)."""

    def _login(sub: str = "user-1", email: str | None = None):
        email = email or f"{sub}@example.com"
        claims = GoogleClaims(
            sub=sub, email=email, email_verified=True, name="Tester", picture=None
        )
        monkeypatch.setattr(routes, "verify_google_id_token", lambda _t: claims)
        r = client.post("/api/auth/google", json={"id_token": "id-token"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


# ---- Mini fragrance catalog (read-only, separate sqlite file) ----------------

# Columns the catalog feature-builder / hydration queries need. Everything the
# mini catalog reads must exist here (mirrors the real `fragrances` table).
_MINICAT_COLUMNS = """
id INTEGER PRIMARY KEY, url TEXT, name TEXT, brand TEXT, year INTEGER,
rating REAL, votes INTEGER,
longevity_very_weak INTEGER, longevity_weak INTEGER, longevity_moderate INTEGER,
longevity_long_lasting INTEGER, longevity_eternal INTEGER,
sillage_intimate INTEGER, sillage_moderate INTEGER, sillage_strong INTEGER,
sillage_enormous INTEGER,
rating_love INTEGER, rating_like INTEGER, rating_ok INTEGER,
rating_dislike INTEGER, rating_hate INTEGER,
season_spring INTEGER, season_summer INTEGER, season_fall INTEGER,
season_winter INTEGER, time_day INTEGER, time_night INTEGER,
gender_female INTEGER, gender_more_female INTEGER, gender_unisex INTEGER,
gender_more_male INTEGER, gender_male INTEGER,
price_way_overpriced INTEGER, price_overpriced INTEGER, price_ok INTEGER,
price_good_value INTEGER, price_great_value INTEGER,
top_notes_json TEXT, middle_notes_json TEXT, base_notes_json TEXT,
accords_json TEXT, image_url TEXT, availability TEXT, in_production INTEGER,
shop_count INTEGER, featured_price REAL, price_min REAL, price_max REAL,
currency TEXT
"""


def _build_mini_catalog(path: str, n: int = 20) -> None:
    """Create a tiny catalog DB with `n` recommendable fragrances (votes=100,
    rating=4.5 → all in the pool), plus two out-of-pool frags (below the votes
    floor / below the Bayesian floor) and a `notes` table for /api/notes +
    note_stats. Pool frags alternate between two brands and carry distinct
    note pyramids so the recommender has features to learn from."""
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE fragrances ({_MINICAT_COLUMNS})")
    conn.execute("CREATE TABLE notes (name TEXT, image_url TEXT)")

    def insert(fid, name, brand, votes, rating, top, base):
        conn.execute(
            "INSERT INTO fragrances (id, url, name, brand, year, rating, votes,"
            " rating_love, rating_like, rating_ok, rating_dislike, rating_hate,"
            " longevity_eternal, sillage_strong, gender_unisex, season_spring,"
            " in_production, top_notes_json, middle_notes_json, base_notes_json,"
            " accords_json, image_url)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fid, f"https://x/{fid}", name, brand, 2020, rating, votes,
                40, 30, 20, 5, 5,
                30, 40, 100, 100,
                1,
                f'[{{"name": "{top}", "strength_pct": 80}}]',
                '[{"name": "Rose", "strength_pct": 60}]',
                f'[{{"name": "{base}", "strength_pct": 70}}]',
                '[{"name": "Fresh", "strength_pct": 50}]',
                f"https://x/{fid}.png",
            ),
        )

    for i in range(1, n + 1):
        brand = "Citrus Co" if i % 2 == 1 else "Wood Co"
        top = "Bergamot" if i % 2 == 1 else "Grapefruit"
        base = "Sandalwood" if i % 2 == 0 else "Amber"
        insert(i, f"Frag {i}", brand, 100, 4.5, top, base)

    # Out-of-pool frags (never recommendable / never searchable).
    insert(n + 1, "Low Votes", "Citrus Co", 5, 3.0, "Bergamot", "Amber")
    insert(n + 2, "Low Bay", "Wood Co", 100, 3.0, "Grapefruit", "Sandalwood")

    # Note images used by /api/notes + note_stats.
    conn.executemany("INSERT INTO notes (name, image_url) VALUES (?, ?)", [
        ("Bergamot", "https://x/bergamot.png"),
        ("Rose", "https://x/rose.png"),
        ("Sandalwood", "https://x/sandalwood.png"),
    ])
    conn.commit()
    conn.close()


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    """Point the app's catalog at a fresh temp mini-catalog and reset the
    per-user recommender + ordering caches so each test starts clean."""
    path = tmp_path / "fragrances.db"
    _build_mini_catalog(str(path))
    monkeypatch.setattr(catalog_mod, "catalog", Catalog(str(path)))
    recommender.reset_caches()
    return catalog_mod.catalog
