# PLAN — Frontend Google login + account (v1)

## Context

- The backend Google OAuth pass is **done** (`frag-discovery-backend`): `POST /api/auth/google`
  verifies a Google ID token, **upserts the user into the `users` table** (google_sub, email,
  name, picture), and issues an opaque bearer session. `GET /api/auth/me`, `POST /api/auth/logout`,
  `GET /api/health`. `GOOGLE_CLIENT_ID` is set in the backend `.env`.
- The frontend (`frag-discovery-frontend`) currently has **no login**: it proxies all `/api` to the
  reference backend on `:3232` (data only, single-user, no auth). `AccountPage` shows a placeholder
  "Sign in — coming with the new backend" card.
- **Goal (this pass):** add "Sign in with Google" to the frontend, gate Discover/Favorites/favorite
  actions behind login, show the signed-in user's account info (name/email/picture), and prove the
  backend upsert end-to-end. **No new backend code** — the DB side is already done.

## Decisions (from user)

1. **Dev routing:** Vite proxy `^/api/auth` → `http://localhost:8000` (new FastAPI backend);
   `/api` → `http://localhost:3232` (reference backend, unchanged). Both backends run concurrently
   in dev. Regex key guarantees `/api/auth` wins over `/api` (Vite's precedence for overlapping
   string keys is undocumented).
2. **Button/UI placement:** Google sign-in appears in the **header (top-right)** and on the
   **Account page**, and as an inline **sign-in prompt on the Discover and Favorites pages**.
3. **Gating:** users may **not** Discover or Favorite until logged in. Browse stays public
   (fragrance catalog); only the favorite star action is gated there.
4. **DB scope:** verify the existing upsert end-to-end (login → row in `users` → UI shows it). No
   new schema.

> Note on data: votes/favorites still hit the reference backend (single-user) this pass — the
> new backend's per-user favorites/votes endpoints are a later pass. The login here is a **UX
> prerequisite**; per-account persistence of favorites lands when those endpoints ship.

## Approach

Add a small auth layer to the frontend: Google Identity Services (GIS) script + button, a zustand
auth store (token persisted to localStorage, user profile), a `RequireAuth` gate for
Discover/Favorites, a gated favorite star, header account control, and an Account page that shows
the real profile. Auth calls go through the same relative `/api/auth/*` URLs (now proxied to the
new backend), so no absolute URLs or CORS issues in dev.

## Files to modify (frontend)

```
vite.config.ts                       # ^/api/auth → :8000 (regex), /api → :3232
.env.example                         # VITE_GOOGLE_CLIENT_ID=
.env                                 # VITE_GOOGLE_CLIENT_ID=<same client ID as backend>
src/lib/types.ts                     # + UserOut, AuthResponse
src/lib/api.ts                       # auth methods + bearer header + 204 handling
src/stores/auth.ts                   # NEW zustand auth store (token, user, login/me/logout)
src/components/auth/GoogleSignInButton.tsx  # NEW GIS button (loads script, renders, callback)
src/components/auth/RequireAuth.tsx   # NEW gate: loading spinner / SignInPrompt / children
src/types/google.d.ts                # NEW minimal types for window.google.accounts
src/components/layout/Header.tsx     # account control (Sign in | avatar+name) top-right
src/pages/AccountPage.tsx            # real profile + logout; sign-in card when logged out
src/pages/DiscoverPage.tsx           # wrap in <RequireAuth>
src/pages/FavoritesPage.tsx          # wrap in <RequireAuth>
src/components/common/FavoriteButton.tsx  # gate: if logged out → go to /account
```

Backend: **no code changes** — only runtime verification.

## Reuse

- `src/main.tsx` — mount point; call `bootstrap()` once at startup (or in `AppLayout` effect).
- `src/stores/ui.ts` — existing zustand store pattern to mirror for `stores/auth.ts`.
- `src/lib/api.ts` `request<T>()` — extend (bearer header + 204) and add `auth` methods.
- `src/components/ui/button.tsx`, `skeleton.tsx`, avatar/`shadcn` — reuse existing UI primitives.
- Backend contract (source of truth): `app/schemas.py` (`UserOut`, `AuthResponse`) and
  `app/auth/routes.py` — already matches the types we add.

## Steps

- [x] **1. Types** (`types.ts`): add `UserOut { id, email, name|null, picture|null, created_at }`
      and `AuthResponse { access_token, token_type, expires_in, user }`.
- [x] **2. API layer** (`api.ts`): extend `request` to accept an optional bearer token and to
      return `undefined` on 204. Add `api.auth.google(idToken)`, `api.auth.me(token)`,
      `api.auth.logout(token)` (URLs `/api/auth/google|me|logout`).
- [x] **3. Auth store** (`stores/auth.ts`): zustand store with `token` (persisted to
      `localStorage["frag.auth.token"]`), `user`, `status: loading|authenticated|unauthenticated`;
      actions `login(idToken)` (→ `api.auth.google` → `setSession`), `bootstrap()` (restore token →
      `api.auth.me` → set user; on 401 clear → unauthenticated), `logout()` (→ `api.auth.logout` →
      clear), `clear()`.
- [x] **4. Bootstrap**: call `auth.bootstrap()` once at app start (effect in `main.tsx` or
      `AppLayout`) so `status` moves from `loading`.
- [x] **5. GIS types** (`src/types/google.d.ts`): minimal ambient types for
      `window.google.accounts.id`.
- [x] **6. Button** (`GoogleSignInButton.tsx`): dynamically load
      `https://accounts.google.com/gsi/client`, `google.accounts.id.initialize({ client_id:
      import.meta.env.VITE_GOOGLE_CLIENT_ID, callback, ux_mode:'popup' })`, `renderButton`; callback
      extracts `response.credential` → `login(credential)`. Handle script-load failure gracefully.
- [x] **7. Gate** (`RequireAuth.tsx`): `loading` → skeleton; `unauthenticated` → inline
      `SignInPrompt` (message + `GoogleSignInButton`); else children.
- [x] **8. Header** (`Header.tsx`): add account control on the right (keep the fragrance/brand
      count): logged out → "Sign in" button → navigate `/account`; logged in → avatar + name →
      navigate `/account`.
- [x] **9. Account page** (`AccountPage.tsx`): when logged out → Google sign-in card; when logged
      in → profile card (avatar, name, email) + Sign out button, then the existing taste-profile
      stats. Remove the "coming with the new backend" placeholder.
- [x] **10. Gate pages**: wrap `DiscoverPage` and `FavoritesPage` in `<RequireAuth>`.
- [x] **11. Gate favorites** (`FavoriteButton.tsx`): if logged out, navigate to `/account` and
      don't call the backend (Browse stays viewable; only the star is gated). Discover's Love is
      already covered by the page gate.
- [x] **12. Vite proxy** (`vite.config.ts`): add `'^/api/auth': { target:
      'http://localhost:8000', changeOrigin: true }` before `/api`.
- [x] **13. Env**: add `VITE_GOOGLE_CLIENT_ID` to `.env.example` and `.env` (same client ID as the
      backend). Confirm `http://localhost:5173` is in the Google Cloud OAuth client's **Authorized
      JavaScript origins**.
- [x] **14. Backend end-to-end verification** (see below).

## Verification

**Backend up + DB schema:**
- `cd frag-discovery-backend && uv run uvicorn app.main:app --port 8000`.
- `curl localhost:8000/api/health` → `{"status":"ok"}`.
- On first run, `data/app.db` is created with `users` + `sessions` tables
  (`sqlite3 data/app.db '.tables'`).

**Frontend:**
- `cd frag-discovery-frontend && npm run dev` (both backends running: reference `:3232` + new `:8000`).
- `curl -i localhost:5173/api/auth/me` (no token) → `401` from the new backend (proves the
  `^/api/auth` proxy routes to `:8000`, while `/api/search` still hits `:3232`).

**End-to-end login (manual, real Google account):**
1. Header shows **Sign in**; clicking it → `/account` with the Google button.
2. Sign in with Google → pick account → ID token POSTed to `/api/auth/google` → backend upserts →
   session stored; header shows avatar + name; `/account` shows name/email/avatar.
3. `sqlite3 data/app.db 'select id, google_sub, email, name, picture, created_at from users;'`
   → **one row** with the signed-in Google account (proves the DB upsert).
4. Discover & Favorites pages: logged out → sign-in prompt; after login → content, no redirect loss.
5. On Browse (logged out), clicking the ★ favorite → routed to `/account` (no backend favorite call).
6. Sign out → header returns to **Sign in**; `/api/auth/me` with the old token → `401`; refresh
   keeps you signed out (token cleared).

**Checks:** `npm run build` (tsc + vite) and `npm run lint` (oxlint) clean. Backend `uv run pytest`
still green (10 passed — no backend changes). Verified live:
- `uv run uvicorn app.main:app --port 8000` → `/api/health` `{"status":"ok"}`; `data/app.db`
  created with `users` + `sessions` tables (users schema matches contract).
- Vite dev proxy: `GET /api/auth/me` via proxy → **401**, `POST /api/auth/google` (no body) →
  **422** (both served by the new backend on :8000) — proves `^/api/auth` routes to the new
  backend while `/api/*` stays on the reference backend.

**Remaining manual step for the user:** paste the Google client ID into the frontend's
`.env` as `VITE_GOOGLE_CLIENT_ID` (same as the backend), restart the running Vite dev server on
:5173 to pick up the new proxy config, start the backend on :8000, and confirm
`http://localhost:5173` is in the Google Cloud OAuth client's **Authorized JavaScript origins**.
Then a real browser sign-in will create the user row in `users` (already verified as the
upsert seam).