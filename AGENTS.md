# frag-discovery

A public, deployable fragrance-discovery web app built on top of the data and
recommendation work in the `frag-scraper` project (`/home/monke/Projects/frag-scraper`).

## Repos / Layout

Single GitHub **monorepo `frag-discovery`** (private, this repo). The scraper +
reference project stays a **sibling repo** at `/home/monke/Projects/frag-scraper`
(see Reference) — `make sync-catalog` and `make reference-backend` depend on it.

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
    `GET /api/recommend`, `GET /api/fragrance/<id>`. A **core content-based LR
    recommender** (port of frag-scraper's LR arm) is trained **per user** from
    their ratings/favorites (cold-start random → top-P exploit, `REC_MIN_FAVORITES=5`),
    cached per user, persisted via the user's votes in `data/app.db`. The catalog
    (`fragrances.db`) is opened **read-only**; the recommendable pool = 20+ votes
    and ≥ 3.8 Bayesian. `make sync-catalog` symlinks the catalog into `data/`.
  - `pytest` green (auth + data).
- **Frontend** (`frag-discovery-frontend`): Google sign-in (header + Account page +
  inline gate), Discover/Favorites gated behind login, and per-user data calls now
  **send the bearer token** (auto-attached in `api.request`). Vite proxy routes
  `^/api/auth` and `^/api/(favorites|recommend|feedback|fragrance)` → `:8000`;
  Browse (`/api/search`, `/api/stats`, `/api/notes`, `/api/ingredient-stats`) still
  hits the reference backend on `:3232`.
- **Run (use the `Makefile` in the repo root):**
  - `make sync-catalog` — symlink `fragrances.db` into `frag-discovery-backend/data/`
  - `make backend` — new FastAPI backend on `:8000`
  - `make reference-backend` — frag-scraper Flask backend (Browse data) on `:3232`
  - `make frontend` — Vite dev server on `:5173`
  - `make test` / `make lint` / `make install`
- **Next step:** port Browse (`/api/search`, `/api/stats`, `/api/notes`,
  `/api/ingredient-stats`) onto the new backend — restricted to the recommendable
  pool and ranked per-user — plus the recommender upgrades (MMR diversification,
  exploration-decay arm, PPMI-SVD embedding/blend). Details: `plans/browse-swap-and-recommender-upgrades.md`.

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
