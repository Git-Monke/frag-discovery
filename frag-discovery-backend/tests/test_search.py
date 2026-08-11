"""Tests for /api/search (Browse) on the new backend: pool restriction,
filters/conditions, per-user discovery ranking, and pagination."""

import json


def test_search_public_pool_restricted_and_bayesian(client, catalog):
    # Signed out → 200, Bayesian fallback, only recommendable pool frags.
    r = client.get("/api/search?sort=recommended&page_size=100")
    assert r.status_code == 200
    body = r.json()
    assert body["recommended_trained"] is False
    assert body["page"] == 1
    assert body["page_size"] == 100
    assert body["pages"] == 1
    assert body["total"] == 20  # the 20 pool frags only
    assert len(body["results"]) == 20
    for x in body["results"]:
        assert x["votes"] >= 20
        assert x["bayesian_score"] >= 3.8
        assert x["favorited"] is False
        assert x["recommended_score"] is None


def test_search_never_surfaces_out_of_pool_frags(client, catalog):
    # "Low Votes" (id 21, votes=5) and "Low Bay" (id 22, bayes<3.8) must never
    # appear, even when explicitly searched.
    for q in ("", "Low"):
        body = client.get("/api/search", params={"q": q, "page_size": 100}).json()
        ids = [r["id"] for r in body["results"]]
        assert 21 not in ids
        assert 22 not in ids


def test_search_filters(client, catalog):
    body = client.get("/api/search", params={"q": "Frag 3", "page_size": 100}).json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == 3

    body = client.get("/api/search", params={"brand": "Wood Co", "page_size": 100}).json()
    assert body["total"] == 10
    assert all(r["brand"] == "Wood Co" for r in body["results"])

    body = client.get("/api/search", params={"year_min": 2021, "page_size": 100}).json()
    assert body["total"] == 0  # all mini frags are year 2020


def test_search_note_and_at_least_conditions(client, catalog):
    # Accord "Fresh" is on every pool frag.
    body = client.get("/api/search", params={
        "conditions": json.dumps([{"type": "accord", "name": "Fresh"}]),
        "page_size": 100,
    }).json()
    assert body["total"] == 20

    # at_least 2 of {Rose, Bergamot}: Rose is on all, Bergamot on odd ids.
    body = client.get("/api/search", params={
        "conditions": json.dumps(
            [{"type": "at_least", "names": ["Rose", "Bergamot"], "count": 2}]
        ),
        "page_size": 100,
    }).json()
    assert body["total"] == 10
    assert all(r["id"] % 2 == 1 for r in body["results"])


def test_search_recommended_trained_ranks_and_favorited(client, catalog, login):
    h = login()
    for fid in range(1, 6):
        client.post(f"/api/feedback/{fid}", json={"action": "love"}, headers=h)
    client.post("/api/favorites/7", headers=h)  # favorited but not otherwise rated

    body = client.get("/api/search?sort=recommended&page_size=100", headers=h).json()
    assert body["recommended_trained"] is True
    assert len(body["results"]) == 20
    # Full discovery algorithm: MMR exploit picks (recommended_score set) mixed
    # with exploration picks (recommended_score null).
    assert any(r["recommended_score"] is not None for r in body["results"])
    assert any(r["recommended_score"] is None for r in body["results"])
    # Per-user favorited flags: frags 1-5 were loved (love syncs the favorite)
    # and 7 was favorited directly; nothing else is favorited.
    fav_ids = {r["id"] for r in body["results"] if r["favorited"]}
    assert fav_ids == {1, 2, 3, 4, 5, 7}


def test_search_recommended_stable_order_across_requests(client, catalog, login):
    h = login()
    for fid in range(1, 6):
        client.post(f"/api/feedback/{fid}", json={"action": "love"}, headers=h)
    a = client.get("/api/search?sort=recommended&page_size=20", headers=h).json()
    b = client.get("/api/search?sort=recommended&page_size=20", headers=h).json()
    assert [r["id"] for r in a["results"]] == [r["id"] for r in b["results"]]


def test_search_pagination_no_dupes_across_pages(client, catalog, login):
    h = login()
    for fid in range(1, 6):
        client.post(f"/api/feedback/{fid}", json={"action": "love"}, headers=h)

    p1 = client.get(
        "/api/search?sort=recommended&page_size=8&page=1", headers=h).json()
    p2 = client.get(
        "/api/search?sort=recommended&page_size=8&page=2", headers=h).json()
    ids1 = {r["id"] for r in p1["results"]}
    ids2 = {r["id"] for r in p2["results"]}
    assert len(ids1) == 8
    assert len(ids2) == 8
    assert ids1.isdisjoint(ids2)
