# frag-discovery-frontend

The web app for **Fragrance Discovery** — a recommender-first fragrance browser
built with React + Vite + TypeScript + Tailwind + shadcn/ui.

Three primary pages plus an account view:

- **Browse** — a large grid of fragrances (Fragrantica-Explorer-style), always
  ranked by **"Recommended for you"** (no other sort options). Star to
  favorite; a top-corner **% match** badge appears on every tile once your
  taste model is trained. Filters (search, brand, year, rating, votes,
  longevity/sillage/season/gender, availability, note conditions) narrow the
  pool before ranking.
- **Discover** — rate fragrances **Pass / Interested / Love** one at a time;
  this is what trains the recommender.
- **Favorites** — saved fragrances, **always sorted by "most likely to be my
  favorite"**, each with a % match badge, plus a search bar to filter by
  name/brand.
- **Account** — taste-profile stats (favorites + ratings). Real sign-in
  (email/Google) arrives with the new backend.

## Data / attribution

The catalog is the same ~135k-fragrance dataset the backend serves. The source
site is **not named anywhere in the UI** — there's deliberately no "view on
site" link and no external outbound link.

## Backend contract

The frontend knows **only the backend's HTTP API** (`/api/...`), per the
`frag-discovery` architecture. Right now it runs against the **reference
backend** (the frag-scraper Flask app) so the UI is fully functional; a new
backend will replace it later without touching the frontend.

To run against the reference backend (served on `:3232`):

```bash
# 1) Start the backend (from the frag-scraper repo)
cd ../frag-scraper && python app.py   # serves /api/* on :3232

# 2) Run this frontend (Vite proxies /api → :3232)
cd ../frag-discovery-frontend
npm install
npm run dev        # http://localhost:5173
```

## Scripts

- `npm run dev` — Vite dev server (proxies `/api` to the backend)
- `npm run build` — type-check + production build
- `npm run lint` — oxlint
- `npm run preview` — preview the production build

## Stack

React 19, TanStack Query, Zustand, React Router, Tailwind CSS v4, Radix UI
(shadcn/ui), lucide-react. The dark amber "Explorer" theme mirrors the original
UI's palette.
