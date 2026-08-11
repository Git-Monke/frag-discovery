"""Per-user content-based recommender (L2 logistic regression + full
frag-scraper discovery pipeline).

The catalog feature matrix is global (`app.catalog.catalog.features`); the
per-user taste model is an L2-regularized logistic regression trained on their
favorites/ratings, cached per user and retrained when the profile changes.

Full discovery pipeline (port of frag-scraper/app.py):
  - **Embedding arm** (REC_EMBED_DIM > 0): the sparse note/accord block is
    replaced by the K-dim PPMI-SVD embedding in the train/predict path.
  - **Logit blend** (REC_BLEND, only when the embedding is on): the reduced-dim
    LR and the full one-hot LR are blended P = sigmoid((z_red + alpha*z_1hot)
    / tau) so the love-rich graded top-P cluster of the one-hot arm survives.
  - **MMR diversification** (mmr_select): exploit picks are greedy-MMR'd over
    the notes/accords space + softmax-sampled, so a batch spans scent families
    instead of collapsing onto the top-P mode.
  - **Exploration decay** (explore_rate + discovery_sequence): a fraction of
    picks decays 50% -> 10% over 1000 swipes; exploration slots are P-weighted
    (Gaussian around center=1.0) from outside the MMR window.

The active taste scale is 3-level (RECO_LEVELS=3):
  pass(-1.0) / interested(+1.0) / love(+2.0 == also a favorite).
"""

import zlib

import numpy as np
from scipy.optimize import minimize

from app import catalog as catalog_mod
from app.config import get_settings
from app.models import Favorite, UserFeedback

# --- Taste scale (3-level) ---
FEEDBACK_WEIGHTS = {"pass": -1.0, "interested": 1.0, "love": 2.0}
# Legacy 5-level / binary actions collapse to `pass` on the 3-level scale.
LEGACY_FEEDBACK = {"skip": "pass", "unknown": "pass", "dislike": "pass", "hate": "pass"}

# --- Settings-driven recommender switches ---
_settings = get_settings()
REC_EMBED_DIM = _settings.rec_embed_dim
REC_BLEND = _settings.rec_blend

# --- Training constants (match frag-scraper/app.py defaults) ---
REC_MIN_FAVORITES = 5        # positive signals (favs + interested) to unlock training
REC_SYNTH_NEG_MULT = 2       # synthetic negatives = mult * n_pos when negatives scarce
REC_SYNTH_NEG_MAX = 200
REC_SYNTH_NEG_WEIGHT = 0.3   # synthesized negatives logged at weak strength
REC_TRAIN_CAP = 2000         # most-recent actions used for training
REC_TRAIN_EVERY = 5          # retrain at most every N calls (or when profile changes)
REC_EXPLORE_START = 0.50     # exploration fraction at 0 swipes
REC_EXPLORE_END = 0.10       # ...decaying linearly to this at REC_EXPLORE_DECAY_SWIPES
REC_EXPLORE_DECAY_SWIPES = 1000
REC_EXPLORE_CENTER = 1.0     # exploration slots concentrate near this P(favorite)
REC_EXPLORE_UNCERTAINTY_TAU = 0.15  # Gaussian width around REC_EXPLORE_CENTER

# --- Exploit diversification (MMR + softmax) ---
REC_MMR_LAMBDA = 0.1          # diversity vs P trade-off in the MMR score
REC_MMR_CANDIDATES = 500      # MMR window: top-P candidates diversified
REC_SOFTMAX_TOPK = 5          # softmax-sample among the top-k MMR scorers
REC_SOFTMAX_TAU = 0.25        # temperature (<1 sharpens toward the best candidate)

# --- Embedding logit blend ---
REC_BLEND_ALPHA = 4.0         # one-hot arm weight in the blend
REC_BLEND_TAU = 8.0           # re-grades served probabilities so MMR can discriminate


class LRModel:
    """L2 logistic-regression recommender: (w, b) + sigmoid."""

    def __init__(self, w, b):
        self.w = np.asarray(w, dtype=np.float64)
        self.b = float(b)

    def predict_proba(self, X):
        logits = X @ self.w + self.b
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))


class BlendLRModel:
    """Reduced-dim LR blended with the full one-hot LR in logit space.

    P = sigmoid((z_reduced + ALPHA * z_onehot) / TAU). The reduced arm alone
    saturates pool P near 1.0 so MMR degenerates to pure diversity and misses
    the loves; the one-hot arm's graded top-P cluster is love-rich. Blending
    re-surfaces the loves and TAU re-grades the served probabilities so MMR /
    exploration can discriminate inside the candidate set. Needs both feature
    matrices (same row order): `X_reduced` (rec_matrix rows) and `X_onehot`
    (features["matrix"] rows). Port of frag-scraper `_BlendLRModel`.
    """

    def __init__(self, w_r, b_r, w_o, b_o, alpha, tau):
        self.w_r = np.asarray(w_r, dtype=np.float64)
        self.b_r = float(b_r)
        self.w_o = np.asarray(w_o, dtype=np.float64)
        self.b_o = float(b_o)
        self.alpha = float(alpha)
        self.tau = float(tau)

    def predict_proba(self, X_reduced, X_onehot):
        z = (X_reduced @ self.w_r + self.b_r) + self.alpha * (
            X_onehot @ self.w_o + self.b_o
        )
        z = z / self.tau
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def model_proba(model, row_ix):
    """P(favorite) for catalog feature rows, dispatching on the model type.

    row_ix: np.int64 array aligned to `catalog.features["ids"]`. The blended
    model needs both feature matrices (reduced + full one-hot) at the same
    rows; plain LR takes the recommender matrix rows only.
    """
    catalog = catalog_mod.catalog
    if isinstance(model, BlendLRModel):
        return model.predict_proba(
            catalog.rec_matrix[row_ix], catalog.features["matrix"][row_ix]
        )
    return model.predict_proba(catalog.rec_matrix[row_ix])


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
    X = catalog.rec_matrix  # reduced [dense|brands|emb] matrix when embedding is on
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
    if REC_EMBED_DIM and REC_BLEND:
        # Blend arm: same rows, full one-hot features (dense + notes + accords
        # + brands). Trained with the identical labels/weights so both arms
        # read the same taste profile. Port of frag-scraper's blend branch.
        rows_ix = np.array(rows, dtype=np.int64)
        X_full = F["matrix"][rows_ix].toarray().astype(np.float64)
        w_o, b_o = _train_lr(X_full, y_arr, sample_w)
        return BlendLRModel(w_r, b_r, w_o, b_o, REC_BLEND_ALPHA, REC_BLEND_TAU)
    return LRModel(w_r, b_r)


# Per-user model cache: user_id -> {"sig", "calls", "model"}.
_USER_CACHE: dict[int, dict] = {}


def get_model(db, user_id: int):
    """Cached per-user model; retrains at most every REC_TRAIN_EVERY calls or
    immediately when the profile (favorites ∪ feedback) changes. Returns an
    LRModel or BlendLRModel, or None when the profile can't train yet."""
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


# ---- Explore schedule ----

def explore_rate(n_swipes: int) -> float:
    """Current exploration fraction: linear decay from REC_EXPLORE_START
    (0 swipes) to REC_EXPLORE_END at REC_EXPLORE_DECAY_SWIPES swipes."""
    if n_swipes >= REC_EXPLORE_DECAY_SWIPES:
        return REC_EXPLORE_END
    t = n_swipes / REC_EXPLORE_DECAY_SWIPES
    return REC_EXPLORE_START + (REC_EXPLORE_END - REC_EXPLORE_START) * t


# ---- MMR diversification ----

def mmr_select(cand_ids, cand_p, F, n, rng):
    """Greedy MMR selection with softmax sampling (port of frag-scraper
    `_mmr_select`). Picks n items from (cand_ids, cand_p), aligned by
    position. At each step every remaining candidate scores
    p - REC_MMR_LAMBDA * max cosine sim to the already-picked set, then the
    next pick is softmax-sampled among the top REC_SOFTMAX_TOPK scorers
    (temperature REC_SOFTMAX_TAU). Similarity uses the notes/accords feature
    block only — not the dense stats / brand dims — so the diversity penalty
    tracks scent similarity. Returns [(frag_id, p), ...] in pick order.
    """
    if n <= 0 or not cand_ids:
        return []
    n = min(n, len(cand_ids))
    id_row = {fid: i for i, fid in enumerate(F["ids"])}
    lo = F["n_dense"]
    hi = lo + F["n_notes"] + F["n_accords"]
    rows = np.array([id_row[f] for f in cand_ids], dtype=np.int64)
    X = F["matrix"][rows][:, lo:hi].toarray().astype(np.float64)
    norms = np.linalg.norm(X, axis=1)
    norms[norms <= 1e-12] = 1.0
    X /= norms[:, None]

    p = np.asarray(cand_p, dtype=np.float64)
    remaining = list(range(len(cand_ids)))
    picked = []
    picked_rows = []
    for _ in range(n):
        rem = np.array(remaining, dtype=np.int64)
        if picked_rows:
            sim = (X[rem] @ X[picked_rows].T).max(axis=1)
        else:
            sim = np.zeros(len(rem))
        mmr = p[rem] - REC_MMR_LAMBDA * sim
        k = min(REC_SOFTMAX_TOPK, len(rem))
        top = np.argsort(-mmr, kind="stable")[:k]
        z = mmr[top] / REC_SOFTMAX_TAU
        w = np.exp(z - z.max())
        gi = int(rem[top[rng.choice(k, p=w / w.sum())]])
        picked.append((cand_ids[gi], float(p[gi])))
        picked_rows.append(gi)
        remaining.remove(gi)
    return picked


# ---- Discovery ordering (shared by Discover + Browse) ----

# Ordering cache for the browse (search) path: (user_id, profile_sig,
# filter_sig) -> full discovery-ordered sequence [(id, p, exploration)].
# Kept small; cleared when full. Profile changes (new favorites/ratings)
# change profile_sig so cached orderings are invalidated automatically.
_ORDER_CACHE: dict[tuple, list] = {}
_ORDER_CACHE_MAX = 8


def reset_caches() -> None:
    """Drop cached per-user models + discovery orderings (used by tests)."""
    _USER_CACHE.clear()
    _ORDER_CACHE.clear()


def seeded_rng(db, user_id: int) -> np.random.RandomState:
    """Deterministic RNG for a user's profile — stable browse ordering across
    page fetches (unlike the unseeded Discover batches)."""
    fav_ids, fb_rows = _load_profile(db, user_id)
    fb_map = _feedback_map(fb_rows)
    sig = _profile_signature(fav_ids, fb_map)
    return np.random.RandomState(zlib.crc32(str(sig).encode()))


def discovery_sequence(db, user_id: int, candidates, rng=None, limit=None,
                       cache_key=None) -> list[dict]:
    """Full discovery-ordered ranking of `candidates` (frag ids) for a user.

    Pipeline (mirrors frag-scraper's recommend flow):
      1. Score every candidate with the per-user model (blended when the
         embedding path is on); sort by P desc.
      2. Exploit: greedy MMR + softmax over the top-P window for the picks the
         caller needs (never consuming the whole window into one batch).
      3. Exploration: reserve round(seq_len * explore_rate(swipes)) slots
         filled by P-weighted (Gaussian, center=1.0) picks from outside the
         exploit picks, flagged exploration (p=None).

    `limit` = batch mode (Discover): returns at most `limit` items = exploit
    picks + exploration picks (mirrors /api/recommend). `limit=None` =
    sequence mode (Browse): returns the FULL order of every candidate with
    exploration sprinkled at deterministic intervals — the caller slices
    pages. Returns [] when the model isn't trained yet (callers fall back).
    """
    model = get_model(db, user_id)
    if model is None or not candidates:
        return []
    if cache_key is not None and cache_key in _ORDER_CACHE:
        return [{"id": fid, "p": p, "exploration": e}
                for fid, p, e in _ORDER_CACHE[cache_key]]

    catalog = catalog_mod.catalog
    F = catalog.features
    id_row = {fid: i for i, fid in enumerate(F["ids"])}
    cand = [f for f in candidates if f in id_row]
    if not cand:
        return []

    rng = rng or np.random.RandomState()
    row_ix = np.array([id_row[f] for f in cand], dtype=np.int64)
    probs = model_proba(model, row_ix)
    order = np.argsort(-probs, kind="stable")
    ranked = [cand[i] for i in order]
    p_map = {fid: float(probs[i]) for i, fid in enumerate(cand)}

    # Exploit/explore split at the current decayed rate.
    fav_ids, fb_rows = _load_profile(db, user_id)
    fb_map = _feedback_map(fb_rows)
    n_swipes = len(fav_ids | set(fb_map))
    rate = explore_rate(n_swipes)
    seq_len = limit if limit is not None else len(ranked)
    n_explore = round(seq_len * rate)
    if limit is not None and n_explore == 0 and rate > 0:
        n_explore = 1  # a fresh feed always gets at least one explore slot
    n_exploit = max(0, seq_len - n_explore)

    # Exploit: diversified via greedy MMR over the top-P window, limited to the
    # picks actually needed (a batch must not consume the whole window, or
    # there'd be no tail left for exploration).
    n_mmr = min(REC_MMR_CANDIDATES, len(ranked), n_exploit)
    picked = mmr_select(ranked[:n_mmr], [p_map[f] for f in ranked[:n_mmr]], F, n_mmr, rng)
    exploit_ids = [fid for fid, _ in picked]
    exploit_set = set(exploit_ids)
    tail = [fid for fid in ranked if fid not in exploit_set]

    # Exploration: P-weighted Gaussian picks from the tail (outside the MMR
    # picks), so exploration slots branch away from the top-P cluster.
    explore_ids: list[int] = []
    if tail and n_explore > 0:
        tail_arr = np.array(tail, dtype=np.int64)
        tail_p = np.array([p_map[f] for f in tail])
        logits = -((tail_p - REC_EXPLORE_CENTER) ** 2) / (
            2.0 * REC_EXPLORE_UNCERTAINTY_TAU ** 2
        )
        logits -= logits.max()
        weights = np.exp(logits)
        weights /= weights.sum()
        n_ex = min(n_explore, len(tail))
        explore_ids = [int(f) for f in rng.choice(
            tail_arr, size=n_ex, replace=False, p=weights)]

    if limit is not None:
        # Batch mode (Discover): exploit picks + exploration picks.
        out = (
            [{"id": fid, "p": p_map.get(fid), "exploration": False}
             for fid in exploit_ids]
            + [{"id": fid, "p": None, "exploration": True}
               for fid in explore_ids]
        )
        out = out[:limit]
    else:
        # Sequence mode (Browse): full order with exploration sprinkled at
        # deterministic intervals so every page slice carries ~explore_rate.
        explore_set = set(explore_ids)
        base = exploit_ids + [fid for fid in tail if fid not in explore_set]
        out = []
        if explore_ids:
            step = max(1, len(base) // (len(explore_ids) + 1))
            ei = 0
            pos = step
            for i, fid in enumerate(base):
                if ei < len(explore_ids) and i == pos:
                    out.append({"id": explore_ids[ei], "p": None, "exploration": True})
                    ei += 1
                    pos += step
                out.append({"id": fid, "p": p_map.get(fid), "exploration": False})
            while ei < len(explore_ids):
                out.append({"id": explore_ids[ei], "p": None, "exploration": True})
                ei += 1
        else:
            out = [{"id": fid, "p": p_map.get(fid), "exploration": False}
                   for fid in base]

    if cache_key is not None:
        if len(_ORDER_CACHE) >= _ORDER_CACHE_MAX:
            _ORDER_CACHE.clear()
        _ORDER_CACHE[cache_key] = [(s["id"], s["p"], s["exploration"]) for s in out]
    return out


# ---- Batch builder (Discover feed) ----

def recommend_batch(db, user_id: int, limit: int, rng=None) -> dict:
    """Build the /api/recommend payload for a user.

    Cold start (fewer than REC_MIN_FAVORITES positives, or an untrainable
    profile) → random unseen pool picks (p=null, exploration). Once trained →
    the full discovery pipeline: blended-model P ranking, MMR-diversified
    exploit prefix, and P-weighted exploration at the decayed rate.
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

    results = []
    if cold_start:
        picks = rng.choice(pool, size=min(limit, len(pool)), replace=False) if pool else []
        for fid in picks:
            results.append({"id": int(fid), "p": None, "exploration": True})
    else:
        seq = discovery_sequence(db, user_id, pool, rng=rng, limit=limit)
        if not seq:
            cold_start = True
            picks = rng.choice(pool, size=min(limit, len(pool)), replace=False) if pool else []
            for fid in picks:
                results.append({"id": int(fid), "p": None, "exploration": True})
        else:
            results = seq

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