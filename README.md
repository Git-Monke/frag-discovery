# frag-discovery

A fragrance-discovery web app: **Browse** an Explorer-style catalog, **Discover**
one perfume at a time to train a **per-user recommender**, save **Favorites**, and
get a "Recommended for you" feed that gets smarter with every rating.

Monorepo with two components (frontend ↔ backend talk only over HTTP JSON):

```text
frag-discovery/
  frag-discovery-backend/     FastAPI + SQLAlchemy 2.0 (Python) — auth, favorites,
                              feedback, per-user content-based recommender, catalog
  frag-discovery-frontend/    React + shadcn/ui (Vite + TypeScript) — Browse, Discover,
                              Favorites, Account UI
  plans/                      per-pass working plans (also see PLAN.md, AGENTS.md)
```

> **Sibling repo (data source only):** the scraper lives in the separate
> `frag-scraper` repo (`/home/monke/Projects/frag-scraper`). Its `fragrances.db`
> catalog (~135k fragrances) and PPMI-SVD note embeddings are the data source;
> `make sync-catalog` symlinks them in. The old Flask reference backend is no
> longer part of the app.

## Quickstart

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Node.js + npm, and the sibling
`frag-scraper` repo checked out at `../frag-scraper` (for the catalog DB).

```bash
make install         # uv sync (backend) + npm install (frontend)
make sync-catalog    # symlink fragrances.db + note embeddings into frag-discovery-backend/data/
```

**Google OAuth** (only sign-in method): copy the `.env.example` → `.env` in both
subdirs and set the client ID — backend `GOOGLE_CLIENT_ID`, frontend
`VITE_GOOGLE_CLIENT_ID` (same "Web application" client in Google Cloud Console).

```bash
make backend            # FastAPI backend → http://localhost:8000  (auth + browse + discover)
make frontend           # Vite dev server → http://localhost:5173  (proxies /api → :8000)
```

Open **http://localhost:5173** — Browse is public; Discover/Favorites require
Google sign-in.

## Testing / linting / building

```bash
make test    # backend pytest + frontend typecheck/build
make lint    # backend ruff + frontend oxlint
make build   # frontend production build
```

## Project state

- **Done:** Google OAuth auth; per-user Discover/Favorites; the **full**
  discovery recommender (PPMI-SVD embedding + logit blend, MMR diversification,
  exploration decay) powering both Discover and Browse; Browse restricted to
  the recommendable pool and ranked per-user; reference backend retired.
- **Next:** infinite scroll for Browse (pagination for now), plus optional
  upgrades — 5-level taste scale, XGB engine, per-user model persistence.

Details live in `AGENTS.md` (architecture, locked decisions, status) and
`plans/` (per-pass plans). The API contract source of truth is the backend's
auto-generated OpenAPI schema at `http://localhost:8000/openapi.json`.
