# frag-discovery-backend

The API server for **frag-discovery**: accounts/auth (Google OAuth), and
per-user votes, favorites, discovery/browse/search, and the served
recommendation algorithm.

- **Stack:** Python + FastAPI, SQLAlchemy 2.0, SQLite (swap to Postgres by
  changing `DATABASE_URL`). The recommender uses numpy/scipy.
- **Auth:** Google OAuth (ID-token flow) is the **only** sign-in method for now.
  The frontend shows Google's "Sign in with Google" button, sends the ID token
  to `POST /api/auth/google`, and the backend verifies it, then issues an
  opaque bearer-token session (stored hashed, 30-day TTL).
- **Catalog:** read-only access to the fragrance catalog DB (`fragrances.db`,
  copied/symlinked from the `frag-scraper` repo) — see `CATALOG_DB` below.
  The **recommendable pool** (what the recommender and Browse serve) is
  fragrances with **≥ 20 votes and a ≥ 3.8 Bayesian rating**; everything else
  is filtered out as garbage.

## One-time setup

1. Google Cloud OAuth client (see below).
2. Point `CATALOG_DB` at the fragrance catalog, e.g. from the repo root:

   ```bash
   make sync-catalog          # symlinks data/fragrances.db → ../frag-scraper/fragrances.db
   ```

   Deploys can copy the DB instead: `mkdir -p data && cp <path>/fragrances.db data/`
   (or mount it and set `CATALOG_DB`). The catalog is opened **read-only** —
   the app never writes to it.

## One-time Google Cloud setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) →
   **APIs & Services** → **Credentials**.
2. **Create Credentials** → **OAuth client ID** → Application type:
   **Web application**.
3. Under **Authorized JavaScript origins**, add your frontend origin
   (dev: `http://localhost:5173`). No redirect URI or client secret is needed
   for the ID-token flow.
4. Copy the **Client ID** into `.env` as `GOOGLE_CLIENT_ID`. The frontend will
   use the same client ID for its button.

## Run locally

```bash
uv sync                          # install deps + create .venv
cp .env.example .env             # then fill in GOOGLE_CLIENT_ID
make sync-catalog                # (repo root) symlink fragrances.db into data/
uv run uvicorn app.main:app --reload --port 8000
```

Smoke test:

```bash
curl localhost:8000/api/health   # → {"status":"ok"}
```

## Tests

```bash
uv run pytest
```

The auth roundtrip is tested with a stubbed Google ID-token verifier against a
temp SQLite database, and the per-user favorites/feedback/recommend endpoints
are tested against a temp mini-catalog. A real browser login (a real Google ID
token) is verified with the frontend sign-in button.

## API (v1)

| Method | Path                 | Auth      | Description                        |
| ------ | -------------------- | --------- | ---------------------------------- |
| POST   | `/api/auth/google`   | —         | Exchange a Google ID token for a session |
| GET    | `/api/auth/me`       | Bearer    | Current user profile               |
| POST   | `/api/auth/logout`   | Bearer    | Revoke the session (204)           |
| GET    | `/api/favorites`     | Bearer    | List favorites (`?sort=recent\|recommend`) |
| DELETE | `/api/favorites`     | Bearer    | Clear all favorites                |
| POST   | `/api/favorites/<id>`| Bearer    | Favorite a fragrance               |
| DELETE | `/api/favorites/<id>`| Bearer    | Un-favorite a fragrance            |
| POST   | `/api/feedback/<id>` | Bearer    | Record a rating (`pass\|interested\|love`) |
| DELETE | `/api/feedback/<id>` | Bearer    | Undo a rating                      |
| GET    | `/api/recommend`     | Bearer    | Next personalized recommendation batch |
| GET    | `/api/fragrance/<id>`| Optional  | Full fragrance row + `favorited` flag |
| GET    | `/api/health`        | —         | Liveness                           |

All endpoints are JSON under `/api/...`; errors use FastAPI's standard
`{"detail": "..."}` shape.
