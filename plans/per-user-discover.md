# PLAN — Per-user Discover + Favorites with a learning recommender (v3)

## Context

- **Auth is done** (backend `:8000` + frontend Google sign-in). Users can sign in, and the
  Discover/Favorites pages are already gated behind `RequireAuth`.
- **The gap:** all *data* calls still hit the **single-user reference backend** (`frag-scraper/app.py`
  on `:3232`) — `/api/favorites`, `/api/recommend`, `/api/feedback`, `/api/search`, etc. There is no
  per-user persistence and no per-user algorithm. The frontend's data methods don't even send the
  bearer token yet.
- **Goal this pass:** signed-in users get **their own** Discover feed and Favorites, backed by a
  real per-user recommender that *learns* from what they rate on Discover. Walked down from the full
  "swap everything" scope per user decision.

## Scope (locked with user)

**In this pass — move onto the new backend (`:8000`), per-user:**
- `/api/favorites` (GET list/clear, POST/DELETE toggle), `/api/feedback/<id>` (POST/DELETE),
  `/api/recommend`, and `/api/fragrance/<id>` (catalog read + per-user `favorited` flag).
- A **core content-based LR recommender**: global catalog feature matrix (dense + notes + accords +
  top-100 brands), per-user L2 logistic regression over that matrix with synthetic negatives,
  cold-start random until enough positive signals, then rank the unseen pool by P(favorite).
- Frontend: send the bearer token on data calls; route the four endpoints above to `:8000`.

**Explicitly deferred (later passes, per user):** MMR diversification, exploration-decay arm, the
PPMI-SVD embedding/blend arm, and moving Browse (`/api/search`, `/api/stats`, `/api/notes`,
`/api/ingredient-stats`) off the reference backend. Browse stays on `:3232` this pass — its
"Recommended for you" rank and `favorited` flags remain reference-based (the frontend already
optimistically corrects favorited flags in-session).

## Approach

1. **Catalog access (read-only)**: the new backend reads the existing `fragrances.db` catalog
   (135k fragrances) via a read-only `sqlite3` connection (`mode=ro&uri=true`) — never mutates it.
   Point it at the real DB with a symlink via a new `make sync-catalog` target; configurable with
   `CATALOG_DB` env so deploys can copy the file. Per-user votes/favorites live in `data/app.db`.
2. **Global catalog model** (computed lazily + cached, like the reference `_ensure_indexes`):
   catalog globals (mean rating, median votes, price params, mean liked) and the **feature matrix**
   — port `_compute_features` as-is: 36 dense dims (min-max scaled over the pool), note `(layer,
   name)` terms + accords (strength/100, L2 row-normalized), top-100 brand one-hot, pool mask
   (`votes>=20 && bayes>=3.8`). `REC_EMBED_DIM=0`, `REC_USE_BRANDS=1`, `REC_SPARSE_NORM=1`.
3. **Per-user recommender** (port from reference, LR-only): `_train_lr` (scipy L-BFGS-B L2 LR),
   `_train_recommender` (positives = favorites/love + interested; negatives = pass; synthetic weak
   negatives when scarce; class-balance then |weight| sample weights; `REC_MIN_FAVORITES=5` gate),
   `_get_recommender_model` with a **per-user model cache** keyed by `user_id` → `{sig, calls,
   model}` (same signature-invalidation + retrain-every-N as reference). `predict_proba` = `X@w+b`
   sigmoid over `_REC_MATRIX` (== `features.matrix`).
4. **Per-user endpoints** (scoped by the bearer session via `get_current_session`):
   - `POST /api/feedback/<id>` — upsert `user_feedback(user_id, frag_id, action)`; `love` also
     inserts a favorite. `DELETE` removes the rating (and the favorite if it was a love).
   - `POST/DELETE /api/favorites/<id>` — toggle; favoriting logs a `love` feedback row (so ★ on
     Browse/detail trains the model too). `DELETE /api/favorites` clears that user's favorites +
     love rows.
   - `GET /api/favorites?sort=recent|recommend` — same response shape as reference
     (`{count, results, recommender{trained,favorites,levels,sort}}`); `recommend` ranks by P.
   - `GET /api/recommend?limit=` — same shape as reference (`{profile, explore_rate, results}`).
     Cold start → random unseen picks (`p:null, exploration:true`); trained → top-P exploit picks
     (`p, exploration:false`). No explore arm this pass; `explore_rate` still computed/returned for
     contract fidelity.
   - `GET /api/fragrance/<frag_id>` — port `SELECT *` + JSON-parse note/accord columns + `favorited`
     (per-user when a valid token is present). **Optional auth** (works signed-out for Browse detail).
5. **Frontend token plumbing + routing**:
   - `src/lib/token.ts` (no imports) — module-level `getAuthToken()`/`setAuthToken()`.
   - `api.request` auto-attaches `Bearer` when a token is set (reference backend ignores it, so
     catalog endpoints still on `:3232` are unaffected).
   - `stores/auth.ts` updates the token holder on login/bootstrap/logout/clear.
   - `vite.config.ts`: regex proxy `^/api/(favorites|recommend|feedback|fragrance)` → `:8000`
     (before the `/api` → `:3232` fallback), alongside the existing `^/api/auth` → `:8000`.

## API contract (new backend, matches the reference so the frontend needs no type changes)

```
GET  /api/recommend?limit=12            [auth]  → RecommendResponse
POST /api/feedback/<id>  {action}       [auth]  → {ok:true}
DELETE /api/feedback/<id>               [auth]  → {ok:true}
GET  /api/favorites?sort=recent|recommend [auth] → FavoritesResponse
POST /api/favorites/<id>                [auth]  → {favorited:true}
DELETE /api/favorites/<id>              [auth]  → {favorited:false}
DELETE /api/favorites                   [auth]  → {count:0}
GET  /api/fragrance/<id>                [optional auth] → full fragrance row + favorited
```

`profile.levels` keys are `pass/interested/love` (3-level scale) — matches `FEEDBACK_WEIGHTS` and
the frontend `FeedbackLevels` type. `REC_MIN_FAVORITES=5` matches the frontend's hardcoded
`REC_MIN_POSITIVE`.

## Files

**Backend (`frag-discovery-backend/`)**
- `pyproject.toml` — add `numpy`, `scipy` deps.
- `.env.example`, `README.md` — document `CATALOG_DB` (default `data/fragrances.db`).
- `app/config.py` — add `catalog_db: str = "data/fragrances.db"`.
- `app/models.py` — add `Favorite` + `UserFeedback` (both FK→`users`, unique `(user_id, frag_id)`).
- `app/catalog.py` — **NEW**: `Catalog` (read-only connector, globals, feature matrix, `fetch_info`,
  `fragrance_full`); module singleton `catalog`.
- `app/recommender.py` — **NEW**: constants, `FEEDBACK_WEIGHTS`/`LEGACY_FEEDBACK` (3-level),
  `_train_lr`, `train_model`, per-user `get_model`, `recommend_batch`, `explore_rate`.
- `app/routes/data.py` — **NEW**: favorites/feedback/recommend/fragrance routers.
- `app/auth/dependencies.py` — add `get_optional_user` (returns `User | None`, no raise).
- `app/main.py` — include the data router.
- `tests/conftest.py` — add a temp mini-catalog fixture + monkeypatch `app.catalog.catalog`.
- `tests/test_data.py` — **NEW**: per-user scoping, feedback↔favorite sync, love-favorite sync,
  cold-start→trained recommend, fragrance `favorited` flag, 401s without token.
- `Makefile` — add `sync-catalog` (symlink `fragrances.db` into `data/`).

**Frontend (`frag-discovery-frontend/`)**
- `src/lib/token.ts` — **NEW** token holder.
- `src/lib/api.ts` — `request` auto-attaches bearer token.
- `src/stores/auth.ts` — push token into the holder on login/bootstrap/logout/clear.
- `vite.config.ts` — add the per-user regex proxy before the `/api` fallback.

**Docs**
- `AGENTS.md` — update "Current status" / "Next step" to reflect this pass.

## Reuse

- Reference recommender logic ported from `/home/monke/Projects/frag-scraper/app.py`
  (`_compute_features`, `_train_lr`, `_train_recommender`, `_get_recommender_model`, `_explore_rate`,
  `_fetch_frag_info`, `get_fragrance`, `feedback`, `favorites`, `toggle_favorite`, `recommend`).
- `fragrances.db` catalog (read-only, via `make sync-catalog` symlink/copy).
- New backend: `get_current_session` (auth), `get_db`, `create_all` bootstrap, `test_data` can
  mirror `tests/test_auth.py` patterns.
- Frontend: `request`'s existing `token?` param + 204 handling; auth store; existing
  `FavoritesResponse`/`RecommendResponse`/`FeedbackAction` types (no changes).

## Steps

- [x] **1. Backend deps + config**: add `numpy`/`scipy` to `pyproject.toml`; add `catalog_db` to
      `config.py`; document in `.env.example`/`README.md`.
- [x] **2. Models**: `Favorite` + `UserFeedback` (FK→users, unique `(user_id, frag_id)`, indexes).
- [x] **3. `catalog.py`**: read-only connector; globals (mean rating/votes/price/liked); feature
      matrix builder (port `_compute_features`); `fetch_info` + `fragrance_full`; lazy+cached;
      `Catalog` singleton.
- [x] **4. `recommender.py`**: constants + 3-level weights; `_train_lr`; `train_model` (synthetic
      negatives, balance, weights, `REC_MIN_FAVORITES` gate); per-user `get_model` cache;
      `recommend_batch`; `explore_rate`.
- [x] **5. Data routes** (`routes/data.py`): favorites (GET/clear/toggle), feedback (POST/DELETE),
      recommend, fragrance; wire `get_current_session` / `get_optional_user`.
- [x] **6. `main.py`**: include data router.
- [x] **7. Makefile**: `sync-catalog` target; run it to symlink the real `fragrances.db`.
- [x] **8. Backend tests** (`tests/test_data.py` + conftest mini-catalog): green.
- [x] **9. Frontend token**: add `token.ts`, auto-attach in `api.request`, update auth store.
- [x] **10. Frontend proxy**: add `^/api/(favorites|recommend|feedback|fragrance)` → `:8000`.
- [x] **11. AGENTS.md** status update (+ deferred-work doc:
      `plans/browse-swap-and-recommender-upgrades.md`).

## Verification

**Backend:**
- `cd frag-discovery-backend && uv run pytest` — green (existing auth tests + new data tests).
- `make sync-catalog` then start backend. `curl` with a real session token:
  - `GET /api/favorites` → `{count:0, results:[], recommender:{...}}`; `POST /api/favorites/1` →
    `{favorited:true}`; `GET /api/favorites` → count 1.
  - `POST /api/feedback/<id>` `love` → favorite auto-added; `DELETE` → removed.
  - Repeated `GET /api/recommend` → cold-start `p:null` until 5 positive signals, then ranked
    `p` values (`.` drops to `0` on refresh).
  - `GET /api/fragrance/1` signed-out → `favorited:false`; signed-in (favorited) → `true`.
  - `GET /api/favorites` with **no token** → `401`.
- Unit: two users' favorites/feedback are isolated.

**Frontend:**
- `cd frag-discovery-frontend && npm run build && npm run lint`.
- Manual E2E (backend `:8000` + reference `:3232` both up):
  1. Sign in → Discover shows random cold-start picks; rate several **Love/Interested**; after 5
     the banner clears and the feed ranks with **% match** badges (`p` present).
  2. Love a pick → it appears in **Favorites** (sorted by most-likely favorite); ★ from Browse adds
     it too (trains the model).
  3. Sign out → Discover/Favorites gated; sign back in → same per-user favorites/model restored.
  4. Browse/search/stats still work (reference backend).
- Restart the backend → per-user favorites + trained model persist (DB-backed).

## Known limitations (this pass, accepted)

- Browse's "Recommended for you" rank and initial `favorited` flags still come from the reference
  backend until the search swap; frontend self-corrects favorited flags in-session.
- Post-training Discover batches are pure top-P exploit (no MMR/exploration) → can cluster on one
  scent family; MMR + exploration land in a later pass.
- Catalog is read-only; deployers must provide `fragrances.db` (symlink in dev via
  `make sync-catalog`, copy/env `CATALOG_DB` in prod).