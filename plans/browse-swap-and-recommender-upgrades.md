# PLAN — Next pass: Browse swap + recommender upgrades (deferred from v3)

> **STATUS: DONE (v4, `plans/browse-full-discovery.md`).** Both parts shipped:
> Browse (`/api/search`, `/api/stats`, `/api/notes`, `/api/ingredient-stats`)
> moved onto the new per-user backend (pool-restricted, discovery-ranked), and
> the recommender is now the full pipeline (PPMI-SVD embedding d20 + logit
> blend, MMR diversification, exploration decay). The reference Flask backend
> is retired from the app (proxy → `:8000`; `reference-backend` Makefile
> target removed). Still open from this doc's scope: **infinite scroll** and
> the optional upgrades below (RECO_LEVELS=5, XGB, model persistence).

> Everything here was **explicitly deferred** in `plans/per-user-discover.md` (the
> per-user Discover/Favorites pass, v3). This doc keeps the details so the next
> pass can pick them up without re-deriving them from `frag-scraper/app.py`.
> Cross-references are to the reference implementation (single-user Flask) that
> the new per-user backend (`frag-discovery-backend`, FastAPI) is porting from.

## Context

v3 moved **Discover + Favorites** (favorites / feedback / recommend / fragrance
detail) onto the new per-user backend. It did **not** move Browse, and it shipped
the recommender in its **core form** (L2 LR, cold start → top-P exploit). This
pass closes both gaps.

Current state after v3:

- New backend `:8000` serves `/api/auth/*`, `/api/favorites`, `/api/feedback/<id>`,
  `/api/recommend`, `/api/fragrance/<id>` (per-user, read-only catalog).
- Frontend Vite proxy: `^/api/(favorites|recommend|feedback|fragrance)` → `:8000`;
  everything else (`/api/search`, `/api/stats`, `/api/notes`, `/api/ingredient-stats`)
  → reference Flask backend on `:3232`.
- `app/catalog.py` builds the global feature matrix + catalog globals; `app/recommender.py`
  trains per-user LR models (cached per user).

## Part A — Browse swap: move search/stats/notes onto the new backend

### Why / what changes

Browse must become **per-user**: its "Recommended for you" rank uses the same
per-user model, and its `favorited` flags must be per-user. Today those come from
the reference backend (single-user) and the frontend only self-corrects in-session.

### Pool restriction (locked with user during v3 review)

> "The Browse page should model the same frags used to build the feature matrix.
> 20 votes or more, 3.8+ bayesian rating or more only should show up."

The **recommendable pool** (`app/catalog.py` `REC_POOL_MIN_VOTES=20`,
`REC_POOL_MIN_BAYES=3.8`) is the canonical served catalog. The new `/api/search`
must filter to the pool by default (`votes >= 20 AND bayesian >= 3.8`) so Browse
never surfaces low-vote garbage. `Catalog.is_recommendable()` /
`features["pool_ids"]` already exist — reuse them. `/api/fragrance/<id>` should
keep serving any id (detail pages for frags favorited from older sessions).

### Endpoints to port (from `frag-scraper/app.py`, all into `app/routes/data.py`)

1. **`GET /api/search`** — the big one. Port `build_query` + the `search` handler:
   - Query building: `q`, `brand`, `year_min/max`, `rating_min/max`, `votes_min/max`,
     `longevity`(+`longevity_min`), `sillage`(+`sillage_min`), `season`, `gender`,
     `available`, note/accord `conditions` (JSON — `_build_condition_sql`, incl.
     `at_least`), `page`/`page_size`, `order`.
   - Derived score columns (compute in SQL like the reference, using `catalog.globals`):
     `bayesian_score`, `price_value_score`, `love_per_dollar_score`, `most_loved_score`,
     `most_liked_score`, `controversial_score` + all raw vote-bucket columns.
   - **Pool filter**: restrict to the recommendable pool (see above).
   - **`sort=recommended`** (the frontend always sends this — see `toSearchParams`):
     fetch the per-user model (`app.recommender.get_model`), predict P for the
     filtered page, set `recommended_score`, return `recommended_trained` bool; fall
     back to Bayesian + `recommended_trained=false` in cold start. Set `favorited`
     per signed-in user (use `get_optional_user`).
   - `random=1` single-row mode (used by the Discover page? verify — keep parity).
   - Response shape must match the frontend `SearchResponse` in
     `frag-discovery-frontend/src/lib/types.ts` exactly.
2. **`GET /api/stats`** — port `_compute_globals`'s note_stats/accord_stats/brand_list
   plus the existing globals. Add `note_stats`, `accord_stats`, `brand_list` to
   `app/catalog.py` (v3 trimmed them out of `Catalog.globals`).
3. **`GET /api/notes`** — note name → image_url map from the catalog's `notes` table
   (`SELECT name, image_url FROM notes WHERE image_url IS NOT NULL`).
4. **`GET /api/ingredient-stats`** — note_stats + accord_stats under one shape
   (see `IngredientStats` type).

### Contract notes

- `SearchResponse`: `{total, page, page_size, pages, results, recommended_trained?}`.
  `Stats`: `{mean_rating, median_votes, total_count, brand_list, mean_price_value,
  median_price_votes, mean_liked, note_stats, accord_stats}`.
- The frontend computes condensed attributes client-side (`lib/utils.ts` `condensed()`);
  AGENTS.md notes the NEW backend should serve `condensed` as a field later — optional.
- **Vite proxy**: after this lands, change the fallback `'/api'` → `:3232` to also
  point at `:8000` (or drop the fallback entirely). The reference backend stops
  being needed for the app.
- `make reference-backend` / `reference-backend` Makefile target can then be removed.

### Files

- `app/catalog.py` — restore note_stats/accord_stats/brand_list; add a notes-map helper.
- `app/routes/data.py` — add search/stats/notes/ingredient-stats handlers (+ `build_query`).
- `frag-discovery-frontend/vite.config.ts` — point the `/api` fallback at `:8000`.
- `frag-discovery-backend/tests/test_data.py` — search tests (filters, pool filter,
  recommended sort, favorited flags).
- `Makefile` — drop `reference-backend` once verified.

## Part B — Recommender upgrades (defer MMR / exploration / embedding from v3)

v3 shipped the **core LR arm** only. The reference has three more systems that
meaningfully improve feed quality; port them one at a time into `app/recommender.py`.

### 1. MMR diversification (`_mmr_select` in `app.py`)

- **Problem solved:** pure top-P exploit collapses every batch onto one scent
  family (top-k of a peaked distribution IS the mode).
- **What:** greedy MMR over the top `REC_MMR_CANDIDATES` by P — score =
  `p - REC_MMR_LAMBDA * max cosine sim to already-picked` — with softmax sampling
  among the top-k (`REC_SOFTMAX_TOPK=5`, `REC_SOFTMAX_TAU=0.25`). Similarity uses
  the **notes/accords block only** (`features["matrix"][:, n_dense : n_dense+n_notes+n_accords]`).
- **Constants:** `REC_MMR_LAMBDA=0.1`, `REC_MMR_CANDIDATES=500`.
- Wire into `recommend_batch` after ranking: `_mmr_select(cand_ids, cand_p, F, n, rng)`.

### 2. Exploration-decay arm

- **Problem solved:** pure exploit can't discover scent families the model hasn't
  scored; exploration keeps the feed branching.
- **What:** fraction of picks reserved for exploration decays linearly from
  `REC_EXPLORE_START=0.50` (0 swipes) to `REC_EXPLORE_END=0.10` at
  `REC_EXPLORE_DECAY_SWIPES=1000`. Exploration picks are P-weighted, not uniform:
  softmax over `-((p - REC_EXPLORE_CENTER)^2)/(2*tau^2)` with
  `REC_EXPLORE_CENTER=1.0`, `REC_EXPLORE_UNCERTAINTY_TAU=0.15`.
- `explore_rate()` already exists in `app/recommender.py`; add the explore arm to
  `recommend_batch` (results get `exploration: True`, `p: None`).

### 3. PPMI-SVD embedding + blend arm

- **Problem solved:** the full one-hot note/accord block (~thousands of dims) can't
  generalize from few votes; a low-dim PPMI-SVD embedding transfers a vote on one
  fragrance to all fragrances sharing those notes/accords.
- **Reference:** `experiments/note_embeddings/` in frag-scraper (build script +
  `frag_emb_d{K}.npy` / `frag_ids_d{K}.npy`). `REC_EMBED_DIM=K` substitutes the
  note/accord block with the K-dim embedding in train/predict only.
- **Blend:** `_BlendLRModel` — train LR on the reduced matrix AND the full one-hot
  matrix, blend in logit space: `P = sigmoid((z_reduced + ALPHA*z_onehot)/TAU)`,
  `REC_BLEND_ALPHA=4.0`, `REC_BLEND_TAU=8.0`. This re-surfaces the love-rich
  top-P cluster the reduced arm misses.
- Needs `features` to also expose the reduced matrix (`_build_recommender_matrix`
  in app.py) and numpy `.npy` embedding files shipped with the backend.

### Also worth porting

- `RECO_LEVELS=5` option (hate/dislike/unknown/interested/love weights) — the
  frontend currently hardcodes the 3-level `FEEDBACK_WEIGHTS` in `lib/types.ts`
  and `DiscoverPage`'s `LEVELS`; a 5-level scale needs frontend changes too.
- `REC_ENGINE=xgb` (optional; needs xgboost dep).
- Per-user model **persistence**: v3 caches trained models in memory
  (`_USER_CACHE`); on a long-lived deploy, consider persisting trained weights
  (e.g. a `user_models` table or blob cache) so restarts don't retrain cold.
  The **votes/favorites data** already persists in `data/app.db`.

## Out of scope / nice-to-have

- `GET /api/similar/<id>` (Find-Similar / Similar section) — the locked frontend
  decisions removed the Similar UI, so not needed.
- Serving the `condensed` attribute from the backend (AGENTS.md mentions it; the
  frontend still computes it client-side).
- Alembic migrations (still `create_all` bootstrap).
- Postgres switch (one-line `DATABASE_URL` change remains).

## Verification for the next pass

- Backend pytest green (existing + new search tests).
- Frontend `npm run build` + `npm run lint`.
- Proxy: `curl :5173/api/search?q=rose` → 200 **from :8000**; reference backend
  can be stopped and Browse still works.
- Per-user Browse: signed-in "Recommended for you" reflects the user's model
  (cold start → Bayesian + banner; trained → `% match` badges).
- Pool restriction: `votes < 20` or `bayesian < 3.8` frags never appear in search.
- MMR: two consecutive `/api/recommend` batches span scent families (eyeball).
