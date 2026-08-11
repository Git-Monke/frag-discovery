import pytest

from app.auth import routes
from app.auth.google import GoogleClaims, InvalidGoogleTokenError


def _claims(
    *,
    sub: str = "google-user-1",
    email: str = "user1@example.com",
    email_verified: bool = True,
    name: str | None = "Test User",
    picture: str | None = "https://example.com/pic.png",
) -> GoogleClaims:
    return GoogleClaims(
        sub=sub,
        email=email,
        email_verified=email_verified,
        name=name,
        picture=picture,
    )


@pytest.fixture
def fake_google(monkeypatch):
    """Stub the Google verifier so routes can run without the network."""

    def _set(claims: GoogleClaims):
        monkeypatch.setattr(routes, "verify_google_id_token", lambda _token: claims)

    return _set


# --- happy path -------------------------------------------------------------


def test_login_me_logout_roundtrip(client, fake_google):
    fake_google(_claims())

    r = client.post("/api/auth/google", json={"id_token": "valid"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["access_token"]
    assert body["user"]["email"] == "user1@example.com"
    assert body["user"]["name"] == "Test User"

    headers = {"Authorization": f"Bearer {body['access_token']}"}

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "user1@example.com"
    assert me.json()["id"] == body["user"]["id"]

    out = client.post("/api/auth/logout", headers=headers)
    assert out.status_code == 204

    # Token is revoked after logout.
    assert client.get("/api/auth/me", headers=headers).status_code == 401


# --- login edge cases -------------------------------------------------------


def test_login_invalid_token_returns_400(client, monkeypatch):
    def _boom(_token):
        raise InvalidGoogleTokenError("Invalid Google ID token")

    monkeypatch.setattr(routes, "verify_google_id_token", _boom)

    r = client.post("/api/auth/google", json={"id_token": "garbage"})
    assert r.status_code == 400
    assert "Invalid Google ID token" in r.json()["detail"]


def test_login_omits_token_returns_422(client):
    r = client.post("/api/auth/google", json={})
    assert r.status_code == 422


def test_login_upserts_same_user(client, fake_google):
    fake_google(_claims())
    first = client.post("/api/auth/google", json={"id_token": "valid"})
    second = client.post("/api/auth/google", json={"id_token": "valid"})
    assert first.status_code == second.status_code == 200
    # Same Google account → same user id, not a duplicate row.
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
    # Both sessions remain valid (multiple concurrent sessions allowed).
    for token in (first.json()["access_token"], second.json()["access_token"]):
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200


def test_login_refreshes_profile_fields(client, fake_google):
    fake_google(_claims(name="Old Name", picture=None))
    first = client.post("/api/auth/google", json={"id_token": "valid"})
    assert first.json()["user"]["name"] == "Old Name"

    fake_google(_claims(name="New Name", picture="https://example.com/new.png"))
    second = client.post("/api/auth/google", json={"id_token": "valid"})
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert second.json()["user"]["name"] == "New Name"
    assert second.json()["user"]["picture"] == "https://example.com/new.png"


# --- auth-required edge cases -----------------------------------------------


def test_me_without_token_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_garbage_token_401(client):
    headers = {"Authorization": "Bearer not-a-real-session"}
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_logout_without_token_401(client):
    assert client.post("/api/auth/logout").status_code == 401


# --- unit tests of the real Google verifier (no network) --------------------


def test_verify_rejects_unverified_email(monkeypatch):
    def _fake_verify(_token, _request, _audience):
        return {
            "sub": "s1",
            "email": "x@example.com",
            "email_verified": False,
            "name": "X",
        }

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", _fake_verify)
    with pytest.raises(InvalidGoogleTokenError):
        routes.verify_google_id_token("any")


def test_verify_wraps_bad_signature_as_invalid(monkeypatch):
    def _fake_verify(_token, _request, _audience):
        raise ValueError("Signature verification failed")

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", _fake_verify)
    with pytest.raises(InvalidGoogleTokenError):
        routes.verify_google_id_token("bad")
