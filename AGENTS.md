# frag-discovery

A public, deployable fragrance-discovery web app built on top of the data and
recommendation work in the `frag-scraper` project (`/home/monke/Projects/frag-scraper`).

## Repos / Layout

Single GitHub **monorepo `frag-discovery`** (private, this repo). The scraper +
reference project stays a **sibling repo** at `/home/monke/Projects/frag-scraper`
(see Reference) — `make sync-catalog` depends on it.

```text
frag-discovery/
  AGENTS.md                       <- this file
  Makefile                        <- dev commands (see Current status → Run)
  PLAN.md                         <- top-level build plan
  plans/                          <- per-pass working plans
  frag-discovery-backend/         <- API server (Python)
  frag-discovery-frontend/        <- web app (React + shadcn/ui)
```

- `frag-discovery-backend` — the API server: accounts/auth, votes, favorites,
  discovery, browse/search, and the served recommendation algorithm.
- `frag-discovery-frontend` — the browser app: browse page, discover page,
  favorites page, account UI. Knows ONLY the backend's API contract.

## Application

Two components, strictly decoupled:

1. **Backend** (Python) — deployable pretty much anywhere: locally, on an Oracle
   free VM, etc. Serves two things: an endpoint to *discover* fragrances and
   make *votes*, and an endpoint to get *recommendations* (two modes:
   next-recommendation discovery + browse top-100). Stores ALL user votes and
   user data alongside the served algorithm, so user data can later be used to
   build quizzes or retrain models.
2. **Frontend** (React + shadcn/ui) — three primary pages:
   - **Browse** — lots and lots of options, grid squares like the Fragrantica
     Explorer browse page; sorting/filtering (year, rating, votes, longevity,
     sillage, etc. — everything the original frag-scraper frontend had). Star
     to favorite; an ✕ "don't show this" button removes an item from the feed
     and the feedback trains the algorithm.
   - **Discover** — interested / not-interested votes, one perfume at a time;
     this is how the algorithm trains.
   - **Favorites** — saved fragrances.
   - Plus an account log in the top-right corner (account info, votes cast, etc.).

## Non-negotiables

- **Frontend is completely disconnected from the backend.** The frontend only
  knows the API structure; how the backend decides what users see (suggested
  fragrances) is completely disconnected from the frontend. This lets the
  algorithm change/train constantly without touching the deployed frontend.
- The backend persists all user votes + data together with the served algorithm.
- The backend runs anywhere (local dev, Oracle free VM, container, systemd).

## Stack decisions

- **Frontend:** React + shadcn/ui (Vite + TypeScript + Tailwind). Started fresh
  (does not inherit the frag-scraper frontend code, but its API/UX knowledge is
  a reference).
- **Backend:** Python (the data processing/fetching/training is already written
  in C-backed libs — numpy/scipy — so Python stays fast). FastAPI is the
  planned framework (async, auto OpenAPI contract, easy uvicorn deploys).
- **Auth:** Google OAuth (ID-token, "Sign in with Google") is the **only**
  sign-in method for now. No email+password, no emailed tokens — Google verifies
  email. The same Google client ID is used by the frontend (`VITE_GOOGLE_CLIENT_ID`)
  and backend (`GOOGLE_CLIENT_ID`). Opaque bearer-token sessions (stored as
  SHA-256 hashes, 30-day TTL).
- **Data & algorithm:** reuse the existing `fragrances.db` catalog (~135k
  fragrances) and port the content-based recommender from frag-scraper's
  `app.py` (Bayesian ranking + L2 logistic regression over note/accord/brand
  features, PPMI-SVD embedding arm, MMR diversification, exploration decay)
  into a per-user, persisted form.

## Design decisions locked in (2025-08)

- Data source: reuse `frag-scraper`'s `fragrances.db` + port its recommender
  into the new backend (per-user models persisted, not in-process globals).
- Auth: Google OAuth only (no email+password) — see Stack decisions.
- Build order: develop endpoints as the frontend needs them; start with the
  API contract and general structure, then fill in.

## How the two components talk

Only via the backend's HTTP API (JSON over `/api/...`). The frontend uses the
backend's auto-generated OpenAPI schema (FastAPI `/openapi.json`) as the single
source of truth for types — if the backend contract changes, the frontend
regenerates types; no other coupling.

## Current status

- **New backend built** (`frag-discovery-backend`): FastAPI + SQLAlchemy 2.0 +
  SQLite (`data/app.db`, Postgres = one-line env change).
  - **Google OAuth auth pass done** — `POST /api/auth/google` (verifies ID token →
    upserts the user into `users` → issues a bearer session), `GET /api/auth/me`,
    `POST /api/auth/logout`, `GET /api/health`.
  - **Per-user Discover/Favorites pass done** — `favorites` + `user_feedback`
    tables (FK→users, unique `(user_id, frag_id)`), and the data routes:
    `GET/POST/DELETE /api/favorites`, `POST/DELETE /api/feedback/<id>`,
    `GET /api/recommend`, `GET /api/fragrance/<id>`.
  - **Browse on the full discovery algorithm (v4) done** — `/api/search`,
    `/api/stats`, `/api/notes`, `/api/ingredient-stats` now live on this
    backend (the reference Flask backend is retired from the app). The
    recommender is the **full frag-scraper pipeline**: a **PPMI-SVD embedding
    arm** (`REC_EMBED_DIM=20` replaces the note/accord block with a 20-dim
    embedding in train/predict) **logit-blended** with the full one-hot LR
    (`P = sigmoid((z_red + 4·z_1hot)/8)`), **MMR diversification** of exploit
    picks over the notes/accords space (λ=0.1, top-500 window, softmax), and
    the **exploration-decay arm** (50% → 10% over 1000 swipes; P-weighted
    picks flagged `exploration`). `discovery_sequence()` is the single
    pipeline shared by Discover (`/api/recommend`, fresh per batch) and
    Browse (`/api/search?sort=recommended`, deterministic + cached per
    (user, profile, filters) for stable pagination). Browse is **restricted
    to the recommendable pool** (≥20 votes + ≥3.8 Bayesian) for every sort.
    Embeddings are symlinked into `data/embeddings` by `make sync-catalog`;
    `REC_EMBED_DIM=0` falls back to the sparse path.
  - `pytest` green (auth, data, search, stats, recommender units).
- **Frontend** (`frag-discovery-frontend`): Google sign-in, Discover/Favorites
  gated behind login, bearer-token data calls, and a single `/api` Vite proxy
  → `:8000`. Browse ranks by the discovery model (MMR + exploration); the
  `% match` badge renders from `recommended_score` and the
  `recommended_trained` banner shows while the taste profile is cold.
- **Run (use the `Makefile` in the repo root):**
  - `make sync-catalog` — symlink `fragrances.db` + note embeddings into
    `frag-discovery-backend/data/`
  - `make backend` — FastAPI backend on `:8000` (auth + browse + discover)
  - `make frontend` — Vite dev server on `:5173` (proxies `/api` → `:8000`)
  - `make test` / `make lint` / `make install`
- **Next step:** infinite scroll for Browse (pagination stays for now), plus
  optional upgrades from the deferred list — RECO_LEVELS=5 taste scale (needs
  frontend), XGB engine, per-user model persistence across restarts. Details:
  `plans/browse-swap-and-recommender-upgrades.md`.

## Frontend decisions (locked in 2025-10)

The frontend is a Fragrantica-Explorer-style recommender app, but the source
site is **never named or linked anywhere** (scraped data — no outbound links):

- **Attribution:** there is deliberately **no "view on site" button and no
  external link** anywhere. "Fragrantica" never appears in the UI.
- **Browse:** always ranked by **"Recommended for you"** — no other sort
  options (sort is hardcoded in the API layer; the backend falls back to
  Bayesian until the taste model is trained, with a banner). Each grid tile
  shows a top-corner **"% match"** badge once trained. Filters unchanged
  (search, brand, year, rating, votes, longevity/sillage/season/gender,
  availability, note conditions).
- **Detail panel (Browse + Discover):** only **Rating, Votes, Bayesian** as
  headline stats. **Notes, Accords, and Sentiment** (Love/Like/OK/Dislike/Hate)
  stay expanded. No Find-Similar button, no Similar section.
- **Condensed attributes:** longevity, sillage, gender, season, time-of-day,
  and price are shown as a **single term** — every bucket holding **≥ 40%** of
  the group's votes, joined by " / " (e.g. `Moderate / Long Lasting`); top
  bucket if none reaches 40%. Gender collapses to Feminine / Unisex /
  Masculine. Currently computed in `lib/utils.ts` (`condensed()`); the NEW
  backend will serve this as a field instead.
- **Discover:** same condensed treatment + rating/Bayesian/votes + notes +
  accords + sentiment; Pass / Interested / Love feed.
- **Favorites:** always sorted by **"most likely to be my favorite"** (no
  checkbox), each card shows a **% match** badge, plus a **search bar** to
  filter by name/brand.
- **Account:** taste-profile stats (favorites + ratings) plus the signed-in
  Google profile (avatar, name, email) with a Sign out button. **Sign-in is
  required** to use Discover and Favorites, and to favorite anything; Browse
  stays public. Email+password is not a sign-in method — Google OAuth only.

## Reference

The source of truth for data shapes, the recommender, and the browse filters is
the `frag-scraper` repo:

- `app.py` — ranking, similarity index, recommender (LR + embedding), /api/search, /api/recommend, /api/feedback, /api/favorites, /api/similar
- `fragrances.db` — the catalog to reuse/copy
- `frontend/` — prior frontend work (UX reference only)
