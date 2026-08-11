# PLAN — Browse on the full discovery algorithm (v4)

> **STATUS: DONE.** Full discovery algorithm (PPMI-SVD embedding d20 + logit
> blend, MMR diversification, exploration decay) ported and shared by Discover
> + Browse; `/api/search`, `/api/stats`, `/api/notes`, `/api/ingredient-stats`
> moved onto the new backend (pool-restricted); reference backend retired;
> infinite scroll intentionally deferred (pagination kept).

## Context

The per-user pass (v3) shipped a **partial** recommender: L2 LR trained on the
full one-hot feature matrix, serving **pure top-P greedy** exploit with no
diversification, exploration, or embedding arm — and Browse still hits the
reference single-user Flask backend on `:3232`.

This pass ports the **full discovery algorithm** from `frag-scraper/app.py`
(three missing systems — MMR diversification, exploration decay, PPMI-SVD
embedding + logit blend) and makes **Browse actually use it**: the new backend
serves `/api/search` ranked by the per-user discovery pipeline (not pure greedy),
restricted to the recommendable pool, with pagination preserved.

**Infinite scroll is explicitly out of scope** (user: "leave the infinite scroll
off for now and keep pages. We'll do infinite scroll later.")

Reference config for the full algorithm (frag-scraper's own production
`make app-embed`): `REC_EMBED_DIM=20`, `REC_BLEND=1`, `REC_BLEND_ALPHA=4.0`,
`REC_BLEND_TAU=8.0`, `REC_MMR_LAMBDA=0.1`, `REC_MMR_CANDIDATES=500`,
`REC_SOFTMAX_TOPK=5`, `REC_SOFTMAX_TAU=0.25`, exploration 0.50→0.10 over 1000
swipes, `RECO_LEVELS=3` (frontend's scale — 5-level stays out).

## Approach

### Part A — Full discovery algorithm (`frag-discovery-backend`)

**A1. Embedding + blend (catalog):** add to `app/catalog.py`
- `REC_EMBED_DIM = 20`, `REC_EMBED_DIR` → settings (`data/embeddings`),
  `REC_BLEND = True` (module constants reading `get_settings()`).
- `@cached_property rec_matrix` — port of `_build_recommender_matrix`
  (reference `app.py:1213`): when `REC_EMBED_DIM > 0`, load
  `frag_emb_d20.npy` + `frag_ids_d20.npy`, substitute the note/accord block →
  layout `[dense | brands | emb]`; else return `features["matrix"]`. Rows
  aligned to `features["ids"]`; missing frag ids get a zero vector.
- Fail fast with a clear error when the embedding files are missing
  (hint: `make sync-catalog`).

**A2. Model classes + dispatch (`app/recommender.py`):**
- Port `BlendLRModel` (`app.py:1298`): `P = sigmoid((z_reduced + ALPHA *
  z_onehot) / TAU)`; keeps `LRModel`.
- Port `model_proba(model, row_ix)` dispatch (`app.py:1312`): blend needs both
  matrices (`catalog.rec_matrix[row_ix]` + `catalog.features["matrix"][row_ix]`);
  plain LR takes `rec_matrix[row_ix]` only.
- `train_model`: train on `rec_matrix` rows; when `REC_EMBED_DIM and REC_BLEND`,
  ALSO train the one-hot arm on `features["matrix"]` rows (identical labels/
  weights) → `BlendLRModel`; else `LRModel`.

**A3. MMR + exploration (`app/recommender.py`):**
- Port `mmr_select(cand_ids, cand_p, F, n, rng)` (`app.py:1430`) verbatim —
  greedy MMR over top-P candidates, similarity on the notes/accords block only
  (`F["n_dense"] : n_dense+n_notes+n_accords`), softmax-sample top-k.
- Keep `explore_rate(n_swipes)` (already present).

**A4. Unified discovery ordering:** add `discovery_sequence(db, user_id,
candidates, rng) -> list[{id, p, exploration}]` — the full pipeline over an
arbitrary candidate id list:
1. Score candidates via `model_proba`; sort by P desc → `ranked`.
2. Exploit prefix: `mmr_select(ranked[:REC_MMR_CANDIDATES], ..., n=min(500,
   len))` → diversified order; append the remaining `ranked` (the tail).
3. Exploration: `n_explore = round(len(candidates) * explore_rate(n_swipes))`,
   clamped to the tail length; P-weighted Gaussian picks
   (`center=1.0, tau=0.15`) from the tail; insert them at deterministic
   intervals (`step = N // (n_explore+1)`) flagged `exploration: True, p: None`.
- Cold start (model None) → caller decides (recommend: random; search:
  Bayesian fallback).

**A5. Rewire consumers:**
- `recommend_batch(db, user_id, limit, rng=None)` — replace the pure top-P
  branch with `discovery_sequence(...)[:limit]` (unseeded rng → fresh batches).
  Response contract unchanged (profile / explore_rate / results with p +
  exploration). Drop the "deferred" comments.
- **Search (Part B) uses the same `discovery_sequence`** with a seeded rng for
  stable pagination.

### Part B — Browse swap (search/stats/notes on the new backend)

**B1. `app/search.py` (new):** port the Browse query machinery from reference
`app.py`:
- Constants: `VOTE_GROUPS`, `VALID_COLS`, `LONGEVITY_ORDER`, `SILLAGE_ORDER`,
  `SORT_MAP`.
- `min_threshold_sql(full_col, ordered)` (`app.py:55`).
- `build_condition_sql(cond)` (`app.py:468`) — note/accord JSON conditions
  (at_least / accord / top / mid / base / any_note, min/max strength,
  upper_only semantics).
- `build_query(args)` (`app.py:556`) — the SELECT with derived score
  expressions (bayesian, price_value, love_per_dollar, most_loved, most_liked,
  controversial) + all vote-bucket columns; WHERE assembly (q, brand, year,
  rating, votes, gender/season/longevity/sillage presets + min-thresholds,
  available, conditions); `SORT_MAP` ordering.
- **Pool restriction (locked decision):** add `votes >= REC_POOL_MIN_VOTES
  AND (C*m + COALESCE(rating,0)*COALESCE(votes,0)) / (m + COALESCE(votes,0))
  >= REC_POOL_MIN_BAYES` to the WHERE for ALL sorts (not just `recommended`),
  so Browse only surfaces pool frags — including the Bayesian fallback. (The
  reference only adds `votes >= 20` for the recommended sort; the user's locked
  rule is stricter — apply it unconditionally.)

**B2. Routes (`app/routes/data.py`):**
- `GET /api/search` (public, optional auth): port the reference handler
  (`app.py:818`) — `sort=recommended` (frontend always sends it) → train/fetch
  the model (`recommender.get_model`); untrained → Bayesian fallback,
  `recommended_trained=false`. Trained → score the filtered candidate ids with
  `discovery_sequence` (rng seeded from the profile signature for stable
  pages), slice the page window, re-select full rows via `SELECT ... WHERE id
  IN (...)`, set `recommended_score` + `favorited` (per optional user). Response
  `{total, page, page_size, pages, results, recommended_trained}`. `random=1`
  mode NOT ported (unused by the frontend). Lightweight per-(user, profile_sig,
  filter_sig) ordering cache so page fetches don't re-run MMR.
- `GET /api/stats` — full globals (see A6) → `{...globals}`.
- `GET /api/notes` — `{name: image_url}` from the catalog `notes` table.
- `GET /api/ingredient-stats` — `{notes: note_stats, accords: accord_stats}`.

**A6. Globals (`app/catalog.py`):** extend `Catalog.globals` with the missing
pieces from reference `_compute_globals` (`app.py:236`): `total_count`,
`brand_list`, `note_stats` (+ `image_url` join from `notes`), `accord_stats`.
Keep existing keys (`mean_rating`, `median_votes`, `mean_price_value`,
`median_price_votes`, `mean_liked`).

**B3. Config (`app/config.py`):** add `rec_embed_dim: int = 20`,
`rec_embed_dir: str = "data/embeddings"`, `rec_blend: bool = True`.

**B4. Embeddings shipped:** extend `make sync-catalog` to also symlink
`../frag-scraper/experiments/note_embeddings/out` →
`frag-discovery-backend/data/embeddings` (the `.npy` files stay out of git —
root `.gitignore` already has `*.npy`).

### Part C — Retire the reference backend from the app

- `frag-discovery-frontend/vite.config.ts`: replace the three proxy rules with
  a single `/api` → `http://localhost:8000` (every endpoint now lives on the
  new backend).
- `frag-discovery-frontend/src/pages/BrowsePage.tsx`: error message ":3232" →
  ":8000".
- `Makefile`: drop the `reference-backend` target; `sync-catalog` stays (still
  needs the sibling repo for the catalog DB + embeddings).
- `README.md` + `AGENTS.md`: drop the reference-backend run step; note the
  sibling repo is now only a data source (catalog + embeddings), not a runtime
  dependency.

### Part D — Tests (`frag-discovery-backend/tests/`)

- `conftest.py`: add a `notes` table + rows to the mini catalog (for `/api/notes`
  + `note_stats`); add a few out-of-pool frags (votes < 20 or bayesian < 3.8)
  to assert pool restriction; set `REC_EMBED_DIM=0` in the test env so tests run
  the sparse path (no embedding files needed).
- `test_search.py` (new): filters (q, brand, year, rating, votes, longevity/
  sillage min, season, gender, available), conditions (accord + at_least),
  pool restriction (out-of-pool frags never returned), `sort=recommended`
  trained → `recommended_trained=true` + `recommended_score` + per-user
  `favorited`; untrained → `recommended_trained=false` + Bayesian order;
  pagination (total/pages/page slices, no dupes across pages).
- `test_stats.py` (new): `/api/stats`, `/api/notes`, `/api/ingredient-stats`
  shapes.
- `test_recommender_units.py` (new): `mmr_select` diversity (two picks from a
  peaked distribution span families), `BlendLRModel.predict_proba` on synthetic
  matrices, `discovery_sequence` mixing (exploration flags, p flags, determinism
  with a seeded rng).
- Existing tests stay green (recommend contract unchanged).

### Part E — Docs

- `AGENTS.md` — Current status: Browse on the new backend + full algorithm;
  next step = infinite scroll + optional upgrades (5-level scale, XGB,
  per-user model persistence).
- `plans/browse-swap-and-recommender-upgrades.md` — mark Part A (browse swap)
  + Part B recommender upgrades done; leave infinite scroll / RECO_LEVELS=5 /
  XGB / model persistence as the new deferred list.

## Files to modify

- `frag-discovery-backend/app/catalog.py` — globals extension, `rec_matrix`,
  embed constants.
- `frag-discovery-backend/app/recommender.py` — blend model, `model_proba`,
  `mmr_select`, `discovery_sequence`, `recommend_batch` rewiring.
- `frag-discovery-backend/app/search.py` — **new**: query builder + conditions.
- `frag-discovery-backend/app/routes/data.py` — search/stats/notes/
  ingredient-stats routes.
- `frag-discovery-backend/app/config.py` — embed settings.
- `frag-discovery-backend/tests/conftest.py`, `tests/test_search.py` (new),
  `tests/test_stats.py` (new), `tests/test_recommender_units.py` (new).
- `frag-discovery-frontend/vite.config.ts`, `src/pages/BrowsePage.tsx` (error
  text only).
- `Makefile`, `README.md`, `AGENTS.md`, `plans/browse-swap-and-recommender-upgrades.md`.

## Reuse

- Reference implementation to port (frag-scraper sibling repo, `app.py`):
  `_build_recommender_matrix` (1213), `_BlendLRModel` (1298), `_model_proba`
  (1312), `_train_recommender` blend branch (1500), `_mmr_select` (1430),
  recommend explore/exploit flow (1520-1640), `_explore_rate` (986),
  `_compute_globals` (236), `_build_condition_sql` (468), `build_query` (556),
  `search` (818), `stats`/`notes`/`ingredient-stats` (798-817).
- Already in the new backend: `catalog.features` (the one-hot matrix),
  `catalog.fetch_info`, `catalog.is_recommendable`, `recommender.get_model` /
  `train_model` / `explore_rate` / `_feedback_counts`, the auth dependency
  `get_optional_user`.
- Frontend needs NO type changes — `SearchResponse` (`recommended_trained`),
  `FragranceRow.recommended_score`, `Stats`, `IngredientStats`, `NoteImages`
  already match; `ResultsGrid` already renders the "% match" badge.

## Verification

- `cd frag-discovery-backend && uv run pytest` — all green (existing 20 + new).
- `make lint` (ruff + oxlint) and `cd frag-discovery-frontend && npm run build`.
- Proxy: with the reference backend STOPPED, `curl :5173/api/search?q=rose` →
  200 from `:8000`; same for `/api/stats`, `/api/notes`, `/api/ingredient-stats`,
  `/api/recommend`, `/api/favorites`.
- Pool restriction: `curl :5173/api/search?sort=recommended` never returns a
  frag with `votes < 20` or `bayesian < 3.8`.
- Trained flow: rate ≥5 loves on Discover → Browse shows the "Recommended for
  you" banner gone + "% match" badges; page 1 is diversified (spans scent
  families — eyeball); page 2 has no dupes with page 1.
- Discover feed: two consecutive `/api/recommend` batches diversify (MMR) and
  include `exploration: true` picks at the decayed rate.
- Embedding blend on: backend logs the reduced matrix shape
  (`dense + brands + emb20`); with `REC_EMBED_DIM=0` (env) it falls back to the
  one-hot path and tests still pass.
