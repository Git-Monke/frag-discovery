"""Tests for /api/stats, /api/notes, /api/ingredient-stats on the new backend."""


def test_stats_shape_and_contents(client, catalog):
    body = client.get("/api/stats").json()
    for key in ("mean_rating", "median_votes", "total_count", "brand_list",
                "mean_price_value", "median_price_votes", "mean_liked",
                "note_stats", "accord_stats"):
        assert key in body, key
    # total_count counts EVERY catalog frag (pool + out-of-pool).
    assert body["total_count"] == 22
    assert "Citrus Co" in body["brand_list"]
    assert "Wood Co" in body["brand_list"]

    names = {n["name"] for n in body["note_stats"]}
    assert "Rose" in names
    rose = next(n for n in body["note_stats"] if n["name"] == "Rose")
    assert rose["total"] == 22  # Rose is the middle note on every frag
    assert rose["image_url"] == "https://x/rose.png"
    # Amber has no image in the notes table → null.
    amber = next(n for n in body["note_stats"] if n["name"] == "Amber")
    assert amber["image_url"] is None

    accord_names = {a["name"] for a in body["accord_stats"]}
    assert "Fresh" in accord_names


def test_notes_map(client, catalog):
    body = client.get("/api/notes").json()
    assert body["Bergamot"] == "https://x/bergamot.png"
    assert body["Rose"] == "https://x/rose.png"
    assert "Amber" not in body  # no image_url row in the notes table


def test_ingredient_stats(client, catalog):
    body = client.get("/api/ingredient-stats").json()
    assert set(body) == {"notes", "accords"}
    assert body["notes"] and body["accords"]
    assert all({"name", "total"} <= set(n) for n in body["notes"])
