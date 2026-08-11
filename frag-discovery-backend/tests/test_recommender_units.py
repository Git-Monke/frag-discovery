"""Unit tests for the full discovery algorithm pieces (no HTTP): the logit
blend model, MMR diversification, and the explore-rate schedule."""

import numpy as np
import pytest

from app import recommender
from app.recommender import BlendLRModel, mmr_select


def test_blend_lr_model_predict():
    rng = np.random.RandomState(0)
    Xr = rng.rand(10, 5)
    Xo = rng.rand(10, 20)
    model = BlendLRModel(
        rng.rand(5) - 0.5, 0.1, rng.rand(20) - 0.5, 0.2, 4.0, 8.0
    )
    p = model.predict_proba(Xr, Xo)
    assert p.shape == (10,)
    assert ((p >= 0.0) & (p <= 1.0)).all()
    # Monotone in the reduced logit: with a positive weight on dim 0, higher
    # z_reduced → higher P.
    w_r = model.w_r.copy()
    w_r[0] = 1.0
    m2 = BlendLRModel(w_r, model.b_r, model.w_o, model.b_o, model.alpha, model.tau)
    Xr2 = Xr.copy()
    Xr2[:, 0] += 1.0
    assert (m2.predict_proba(Xr2, Xo) >= m2.predict_proba(Xr, Xo)).all()


def _pair_sim(F, a, b):
    """Cosine similarity of two frags' notes/accords block (the MMR axis)."""
    lo = F["n_dense"]
    hi = lo + F["n_notes"] + F["n_accords"]
    id_row = {fid: i for i, fid in enumerate(F["ids"])}
    X = F["matrix"][[id_row[a], id_row[b]]][:, lo:hi].toarray()
    na = np.linalg.norm(X[0])
    nb = np.linalg.norm(X[1])
    if na == 0 or nb == 0:
        return 0.0
    return float(X[0] @ X[1] / (na * nb))


def test_mmr_select_diversifies():
    # Synthetic feature matrix (the 20-frag mini catalog can't exercise this:
    # REC_NOTE_MIN_DF=50 leaves it with no note columns). 4 frags over 4
    # note/accord dims: 1&3 share note A (identical), 2&4 share note B.
    import numpy as np
    from scipy import sparse

    M = sparse.csr_matrix(np.array([
        [1, 0, 0, 0],  # frag 1: note A
        [0, 1, 0, 0],  # frag 2: note B
        [1, 0, 0, 0],  # frag 3: note A
        [0, 1, 0, 0],  # frag 4: note B
    ], dtype=np.float64))
    F = {"ids": [1, 2, 3, 4], "matrix": M,
         "n_dense": 0, "n_notes": 2, "n_accords": 2, "n_brands": 0}
    # Pure greedy top-2 by P = (1, 3) — identical scent. MMR must pick a pair
    # that is less similar in the notes/accords space.
    cands = [1, 3, 2, 4]
    ps = [0.9, 0.85, 0.8, 0.75]
    picked = mmr_select(cands, ps, F, 2, np.random.RandomState(0))
    ids = [fid for fid, _ in picked]
    assert len(ids) == 2
    greedy_sim = _pair_sim(F, 1, 3)
    mmr_sim = _pair_sim(F, ids[0], ids[1])
    assert mmr_sim < greedy_sim, f"MMR pair {ids} is not more diverse than greedy (1,3)"


def test_mmr_select_returns_p_in_pick_order():
    import numpy as np
    from scipy import sparse

    M = sparse.csr_matrix(np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
    ], dtype=np.float64))
    F = {"ids": [1, 2, 3], "matrix": M,
         "n_dense": 0, "n_notes": 3, "n_accords": 1, "n_brands": 0}
    p_map = {1: 0.5, 2: 0.4, 3: 0.3}
    picked = mmr_select([1, 2, 3], [0.5, 0.4, 0.3], F, 2, np.random.RandomState(3))
    assert len(picked) == 2
    # Each pick carries the caller's P for that id (softmax-sampled, so the
    # first pick is not guaranteed to be the max scorer).
    assert all(pr == p_map[fid] for fid, pr in picked)


def test_explore_rate_decay():
    assert recommender.explore_rate(0) == recommender.REC_EXPLORE_START
    assert recommender.explore_rate(1000) == recommender.REC_EXPLORE_END
    # Linear halfway.
    assert recommender.explore_rate(500) == pytest.approx(
        (recommender.REC_EXPLORE_START + recommender.REC_EXPLORE_END) / 2
    )
    # Clamped after the decay window.
    assert recommender.explore_rate(5000) == recommender.REC_EXPLORE_END
