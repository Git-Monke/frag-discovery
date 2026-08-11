"""Tests for the per-user data endpoints (favorites, feedback, recommend,
fragrance detail) against a temp mini-catalog."""

import pytest

from app.auth import routes
from app.auth.google import GoogleClaims


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


# --- auth gating -------------------------------------------------------------


def test_data_endpoints_require_auth(client, catalog):
    assert client.get("/api/favorites").status_code == 401
    assert client.get("/api/recommend").status_code == 401
    assert client.delete("/api/favorites").status_code == 401
    assert client.post("/api/favorites/1").status_code == 401
    assert client.post("/api/feedback/1", json={"action": "love"}).status_code == 401
    assert client.delete("/api/feedback/1").status_code == 401


# --- recommend: cold start → trained ----------------------------------------


def test_recommend_cold_start_then_trained(client, catalog, login):
    h = login()

    body = client.get("/api/recommend?limit=10", headers=h).json()
    assert body["profile"]["cold_start"] is True
    assert len(body["results"]) == 10
    assert all(x["p"] is None for x in body["results"])
    assert all(x["exploration"] for x in body["results"])

    # 5 loves → model unlocks.
    for frag_id in range(1, 6):
        assert client.post(f"/api/feedback/{frag_id}", json={"action": "love"}, headers=h).json() == {"ok": True}

    body = client.get("/api/recommend?limit=10", headers=h).json()
    assert body["profile"]["cold_start"] is False
    assert len(body["results"]) == 10
    assert all(x["p"] is not None for x in body["results"])
    assert all(not x["exploration"] for x in body["results"])


def test_recommend_profile_levels_and_swipes(client, catalog, login):
    h = login()
    client.post("/api/feedback/1", json={"action": "pass"}, headers=h)
    client.post("/api/feedback/2", json={"action": "interested"}, headers=h)
    client.post("/api/feedback/3", json={"action": "love"}, headers=h)

    body = client.get("/api/recommend", headers=h).json()
    assert body["profile"]["levels"] == {"pass": 1, "interested": 1, "love": 1}
    assert body["profile"]["favorites"] == 1
    assert body["profile"]["swipes"] == 3  # pass + interested + love (frag 3)


# --- feedback ↔ favorites sync ----------------------------------------------


def test_feedback_love_syncs_favorite(client, catalog, login):
    h = login()
    client.post("/api/feedback/3", json={"action": "love"}, headers=h)
    favs = client.get("/api/favorites", headers=h).json()
    assert favs["count"] == 1
    assert favs["results"][0]["id"] == 3

    # Undoing the love removes the favorite too.
    client.delete("/api/feedback/3", headers=h)
    assert client.get("/api/favorites", headers=h).json()["count"] == 0


def test_feedback_invalid_action_400(client, catalog, login):
    h = login()
    r = client.post("/api/feedback/1", json={"action": "bogus"}, headers=h)
    assert r.status_code == 400


# --- favorites toggle / clear / isolation -----------------------------------


def test_favorites_toggle(client, catalog, login):
    h = login()
    assert client.post("/api/favorites/2", headers=h).json() == {"favorited": True}
    assert client.delete("/api/favorites/2", headers=h).json() == {"favorited": False}
    assert client.get("/api/favorites", headers=h).json()["count"] == 0


def test_favorites_clear(client, catalog, login):
    h = login()
    for fid in (1, 2, 3):
        client.post(f"/api/favorites/{fid}", headers=h)
    assert client.get("/api/favorites", headers=h).json()["count"] == 3
    assert client.delete("/api/favorites", headers=h).json() == {"count": 0}
    assert client.get("/api/favorites", headers=h).json()["count"] == 0


def test_favorites_isolated_between_users(client, catalog, login):
    h1 = login(sub="alice")
    h2 = login(sub="bob")
    client.post("/api/favorites/1", headers=h1)
    assert client.get("/api/favorites", headers=h1).json()["count"] == 1
    assert client.get("/api/favorites", headers=h2).json()["count"] == 0


def test_favorites_recommend_sort_ranks(client, catalog, login):
    h = login()
    for fid in range(1, 6):
        client.post(f"/api/feedback/{fid}", json={"action": "love"}, headers=h)

    body = client.get("/api/favorites?sort=recommend", headers=h).json()
    assert body["count"] == 5
    assert body["recommender"]["trained"] is True
    assert all(x["p"] is not None for x in body["results"])


# --- fragrance detail --------------------------------------------------------


def test_fragrance_detail_favorited_flag(client, catalog, login):
    # Signed out → favorited false, notes parsed into arrays.
    r = client.get("/api/fragrance/1")
    assert r.status_code == 200
    assert r.json()["favorited"] is False
    assert r.json()["top_notes_json"] == [{"name": "Bergamot", "strength_pct": 80}]

    # Signed in + favorited → true.
    h = login()
    client.post("/api/favorites/1", headers=h)
    assert client.get("/api/fragrance/1", headers=h).json()["favorited"] is True

    # Signed in but not favorited → false.
    assert client.get("/api/fragrance/2", headers=h).json()["favorited"] is False

    assert client.get("/api/fragrance/9999").status_code == 404