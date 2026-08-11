"""Per-user content-based recommender (L2 logistic regression).

Ports the core of frag-scraper's recommender (LR arm only) into a per-user,
persisted form. The catalog feature matrix is global (`app.catalog.catalog.features`);
each user's taste model is an L2-regularized logistic regression trained on their
favorites/ratings, cached per user and retrained when the profile changes.

The active taste scale is 3-level (RECO_LEVELS=3):
  pass(-1.0) / interested(+1.0) / love(+2.0 == also a favorite).
"""

import zlib

import numpy as np
from scipy.optimize import minimize

from app import catalog as catalog_mod
from app.models import Favorite, UserFeedback

# --- Taste scale (3-level) ---
FEEDBACK_WEIGHTS = {"pass": -1.0, "interested": 1.0, "love": 2.0}
# Legacy 5-level / binary actions collapse to `pass` on the 3-level scale.
LEGACY_FEEDBACK = {"skip": "pass", "unknown": "pass", "dislike": "pass", "hate": "pass"}

# --- Training constants (match frag-scraper/app.py defaults) ---
REC_MIN_FAVORITES = 5        # positive signals (favs + interested) to unlock training
REC_SYNTH_NEG_MULT = 2       # synthetic negatives = mult * n_pos when negatives scarce
REC_SYNTH_NEG_MAX = 200
REC_SYNTH_NEG_WEIGHT = 0.3   # synthesized negatives logged at weak strength
REC_TRAIN_CAP = 2000         # most-recent actions used for training
REC_TRAIN_EVERY = 5          # retrain at most every N calls (or when profile changes)
REC_EXPLORE_START = 0.50     # exploration fraction at 0 swipes (kept for contract shape)
REC_EXPLORE_END = 0.10
REC_EXPLORE_DECAY_SWIPES = 1000


class LRModel:
    """L2 logistic-regression recommender: (w, b) + sigmoid."""

    def __init__(self, w, b):
        self.w = np.asarray(w, dtype=np.float64)
        self.b = float(b)

    def predict_proba(self, X):
        logits = X @ self.w + self.b
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))


def _train_lr(X_dense: np.ndarray, y: np.ndarray, sample_w: np.ndarray, lam: float = 1.0):
    """L2-regularized logistic regression (L-BFGS-B). Returns (w, b)."""
    _, d = X_dense.shape

    def fg(params):
        w = params[:d]
        b = params[d]
        z = X_dense @ w + b
        z = np.clip(z, -30.0, 30.0)
        h = 1.0 / (1.0 + np.exp(-z))
        eps = 1e-12
        loss = -np.sum(sample_w * (y * np.log(h + eps) + (1.0 - y) * np.log(1.0 - h + eps)))
        loss += 0.5 * lam * float(np.dot(w, w))
        diff = (h - y) * sample_w
        grad_w = X_dense.T @ diff + lam * w
        grad_b = float(diff.sum())
        return loss, np.concatenate([grad_w, np.array([grad_b])])

    res = minimize(
        fg, np.zeros(d + 1), method="L-BFGS-B", jac=True,
        options={"maxiter": 300, "ftol": 1e-10},
    )
    return res.x[:d].astype(np.float64), res.x[d]


# ---- Profile helpers (per user, from data/app.db) ----

def _profile_signature(fav_ids, fb_map) -> tuple:
    return (tuple(sorted(fav_ids)), tuple(sorted(fb_map.items())))


def _load_profile(db, user_id: int) -> tuple[set, list]:
    """(favorite ids, feedback rows) for a user."""
    fav_ids = {
        r[0] for r in db.query(Favorite.frag_id).filter(Favorite.user_id == user_id)
    }
    fb_rows = db.query(UserFeedback).filter(UserFeedback.user_id == user_id).all()
    return fav_ids, fb_rows


def _feedback_map(fb_rows) -> dict:
    """frag_id -> weight for a list of feedback rows (legacy actions mapped)."""
    out = {}
    for r in fb_rows:
        a = LEGACY_FEEDBACK.get(r.action, r.action)
        w = FEEDBACK_WEIGHTS.get(a, r.weight or -1.0)
        out[r.frag_id] = w
    return out


def _feedback_counts(fb_rows) -> dict:
    """Per-level counts, zero-filled, on the active 3-level scale."""
    counts = {a: 0 for a in FEEDBACK_WEIGHTS}
    for r in fb_rows:
        counts[LEGACY_FEEDBACK.get(r.action, r.action)] += 1
    return counts


def _positive_signal_count(fav_ids, fb_rows) -> int:
    """favorites + 'interested' ratings — the unlock gate for training."""
    return len(fav_ids) + sum(1 for r in fb_rows if r.action == "interested")


# ---- Training ----

def train_model(db, user_id: int) -> LRModel | None:
    """Train the LR model for a user from their favorites/ratings. Returns None
    when there isn't a usable profile (fewer than REC_MIN_FAVORITES positives)."""
    catalog = catalog_mod.catalog
    fav_ids, fb_rows = _load_profile(db, user_id)
    fb_map = _feedback_map(fb_rows)

    if _positive_signal_count(fav_ids, fb_rows) < REC_MIN_FAVORITES:
        return None

    seen = fav_ids | set(fb_map)
    F = catalog.features
    X = F["matrix"]
    id_row = {fid: i for i, fid in enumerate(F["ids"])}

    fav_sorted = [
        r[0] for r in db.query(Favorite.frag_id)
        .filter(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
        .limit(REC_TRAIN_CAP)
    ]
    fb_sorted = [
        r[0] for r in db.query(UserFeedback.frag_id)
        .filter(UserFeedback.user_id == user_id, UserFeedback.action != "love")
        .order_by(UserFeedback.created_at.desc())
        .limit(REC_TRAIN_CAP)
    ]

    rows, y, sw = [], [], []
    fav_covered = set()
    # Favorites: strong positives at weight 1.0.
    for f in fav_sorted:
        if f in id_row:
            rows.append(id_row[f]); y.append(1.0); sw.append(1.0)
            fav_covered.add(f)
    # Other feedback levels: label by sign, weight by |weight|.
    for f in fb_sorted:
        if f not in id_row or f in fav_covered:
            continue
        w = fb_map.get(f, -1.0)
        rows.append(id_row[f]); y.append(1.0 if w > 0 else 0.0); sw.append(abs(w))

    # Synthetic weak negatives when negatives are scarce.
    pool_unseen = [f for f in F["pool_ids"] if f not in seen]
    rng = np.random.RandomState(zlib.crc32(str(_profile_signature(fav_ids, fb_map)).encode()))
    n_pos = sum(1 for v in y if v > 0)
    n_neg = len(y) - n_pos
    n_synth_target = REC_SYNTH_NEG_MULT * n_pos - n_neg
    if n_synth_target > 0 and pool_unseen:
        n_synth = min(n_synth_target, REC_SYNTH_NEG_MAX, len(pool_unseen))
        synth = rng.choice(pool_unseen, size=n_synth, replace=False)
        for f in synth:
            rows.append(id_row[f]); y.append(0.0); sw.append(REC_SYNTH_NEG_WEIGHT)

    if len(rows) < 2:
        return None

    X_train = X[np.array(rows, dtype=np.int64)].toarray().astype(np.float64)
    y_arr = np.array(y, dtype=np.float64)
    sw_arr = np.array(sw, dtype=np.float64)
    # Class-balance the loss, THEN apply each sample's |weight| from the taste scale.
    n_total = len(y_arr)
    n_pos = float(np.sum(y_arr > 0))
    n_neg = n_total - n_pos
    balance = np.where(y_arr > 0, n_total / (2.0 * n_pos), n_total / (2.0 * n_neg))
    sample_w = balance * sw_arr

    w_r, b_r = _train_lr(X_train, y_arr, sample_w)
    return LRModel(w_r, b_r)


# Per-user model cache: user_id -> {"sig", "calls", "model"}.
_USER_CACHE: dict[int, dict] = {}


def get_model(db, user_id: int) -> LRModel | None:
    """Cached per-user model; retrains at most every REC_TRAIN_EVERY calls or
    immediately when the profile (favorites ∪ feedback) changes."""
    fav_ids, fb_rows = _load_profile(db, user_id)
    fb_map = _feedback_map(fb_rows)
    sig = _profile_signature(fav_ids, fb_map)
    cache = _USER_CACHE.setdefault(user_id, {"sig": None, "calls": 0, "model": None})
    if cache["sig"] != sig or cache["model"] is None or cache["calls"] >= REC_TRAIN_EVERY:
        model = train_model(db, user_id)
        _USER_CACHE[user_id] = {"calls": 0, "sig": sig, "model": model}
        return model
    cache["calls"] += 1
    return cache["model"]


def reset_model_cache() -> None:
    """Drop all cached per-user models (used by tests)."""
    _USER_CACHE.clear()


# ---- Explore schedule (kept for the /api/recommend contract shape; the explore
# arm itself is deferred — see plans/browse-swap-and-recommender-upgrades.md) ----

def explore_rate(n_swipes: int) -> float:
    """Linear decay from REC_EXPLORE_START (0 swipes) to REC_EXPLORE_END."""
    if n_swipes >= REC_EXPLORE_DECAY_SWIPES:
        return REC_EXPLORE_END
    t = n_swipes / REC_EXPLORE_DECAY_SWIPES
    return REC_EXPLORE_START + (REC_EXPLORE_END - REC_EXPLORE_START) * t


# ---- Batch builder ----

def recommend_batch(db, user_id: int, limit: int, rng=None) -> dict:
    """Build the /api/recommend payload for a user.

    Cold start (fewer than REC_MIN_FAVORITES positives) → random unseen pool
    picks (p=null, exploration). Once trained → pure top-P exploit picks from
    the unseen pool. MMR diversification + the exploration arm are deferred.
    """
    catalog = catalog_mod.catalog
    fav_ids, fb_rows = _load_profile(db, user_id)
    fb_map = _feedback_map(fb_rows)
    seen = fav_ids | set(fb_map)
    n_swipes = len(seen)

    cold_start = _positive_signal_count(fav_ids, fb_rows) < REC_MIN_FAVORITES

    F = catalog.features
    pool = [f for f in F["pool_ids"] if f not in seen]
    rng = rng or np.random.RandomState()

    model = None
    if not cold_start:
        model = get_model(db, user_id)
        if model is None:
            cold_start = True

    results = []
    if cold_start or model is None:
        picks = rng.choice(pool, size=min(limit, len(pool)), replace=False) if pool else []
        for fid in picks:
            results.append({"id": int(fid), "p": None, "exploration": True})
    else:
        id_row = {fid: i for i, fid in enumerate(F["ids"])}
        row_ix = np.array([id_row[f] for f in pool], dtype=np.int64)
        probs = model.predict_proba(F["matrix"][row_ix])
        order = np.argsort(-probs, kind="stable")
        for i in order[:limit]:
            results.append({"id": int(pool[i]), "p": float(probs[i]), "exploration": False})

    info = catalog.fetch_info([r["id"] for r in results])
    out = []
    for r in results:
        d = info.get(r["id"])
        if not d:
            continue
        d["p"] = round(r["p"], 4) if r["p"] is not None else None
        d["exploration"] = r["exploration"]
        d["favorited"] = False
        out.append(d)

    return {
        "profile": {
            "favorites": len(fav_ids),
            "levels": _feedback_counts(fb_rows),
            "swipes": n_swipes,
            "cold_start": cold_start,
        },
        "explore_rate": round(explore_rate(n_swipes), 4),
        "results": out,
    }