"""Read-only access to the fragrance catalog DB + the recommender feature matrix.

The catalog (`fragrances.db`) is the shared, read-only source of truth for every
fragrance's static attributes and the derived feature matrix. It is opened with
`sqlite3` in read-only URI mode — the app never writes to it. Per-user state
(favorites, feedback) lives in `data/app.db` instead.

The **recommendable pool** (what the recommender serves, and what Browse will
serve once its search moves over — see `plans/browse-swap-and-recommender-upgrades.md`)
is fragrances with `votes >= REC_POOL_MIN_VOTES` **and** a Bayesian rating
`>= REC_POOL_MIN_BAYES`. This filters out low-vote garbage so only well-reviewed
fragrances are surfaced.
"""

import json
import math
import sqlite3
from functools import cached_property

import numpy as np
from scipy import sparse

from app.config import get_settings

# --- Recommender constants (match frag-scraper/app.py defaults) ---
REC_POOL_MIN_VOTES = 20        # recommendation pool: only frags with votes >= this
REC_POOL_MIN_BAYES = 3.8       # ...and a Bayesian rating >= this (the quality floor)
REC_NOTE_MIN_DF = 50           # note (layer, name) min pool document frequency
REC_USE_BRANDS = True          # include the top-100 brand one-hot block
REC_SPARSE_NORM = True         # L2-normalize the note/accord block per row
N_DENSE = 36                   # dense feature dims (before sparse blocks)


def _shares(*vals) -> list:
    """Normalize a vote bucket into fractional shares; all-zero → zeros."""
    s = sum(v for v in vals if v)
    if s <= 0:
        return [0.0] * len(vals)
    return [(v / s) if v else 0.0 for v in vals]


def _norm_term(name: str) -> str:
    """Normalize a note/accord name: lowercase + collapse whitespace."""
    if not name:
        return ""
    return " ".join(str(name).lower().split())


class Catalog:
    """Lazy, read-only interface to the fragrance catalog + feature matrix."""

    def __init__(self, path: str):
        self._path = path

    def conn(self) -> sqlite3.Connection:
        """A fresh read-only connection (thread-safe; close after use)."""
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- Catalog-wide stats (needed for Bayesian scoring) ----

    @cached_property
    def globals(self) -> dict:
        conn = self.conn()
        C = conn.execute(
            "SELECT AVG(rating) FROM fragrances"
            " WHERE rating IS NOT NULL AND votes IS NOT NULL"
        ).fetchone()[0] or 3.99

        n = conn.execute(
            "SELECT COUNT(*) FROM fragrances WHERE votes IS NOT NULL"
        ).fetchone()[0]
        mid = (n - 1) // 2
        rows = conn.execute(
            f"SELECT votes FROM fragrances WHERE votes IS NOT NULL"
            f" ORDER BY votes LIMIT 2 OFFSET {mid}"
        ).fetchall()
        if n % 2 == 1:
            m = rows[0][0]
        else:
            m = (rows[0][0] + rows[1][0]) / 2 if len(rows) >= 2 else rows[0][0]

        price_rows = conn.execute(
            """
            SELECT
                (1.0*price_way_overpriced + 2*price_overpriced + 3*price_ok
                 + 4*price_good_value + 5*price_great_value)
                / (price_way_overpriced+price_overpriced+price_ok+price_good_value+price_great_value) AS raw_val,
                (price_way_overpriced+price_overpriced+price_ok+price_good_value+price_great_value) AS price_total
            FROM fragrances
            WHERE (price_way_overpriced+price_overpriced+price_ok+price_good_value+price_great_value) > 0
            ORDER BY price_total
            """
        ).fetchall()
        C_price = sum(r[0] for r in price_rows) / len(price_rows) if price_rows else 3.0
        pn = len(price_rows)
        pmid = (pn - 1) // 2
        if pn == 0:
            m_price = 0.0
        elif pn % 2 == 1:
            m_price = price_rows[pmid][1]
        else:
            m_price = (price_rows[pmid][1] + price_rows[pmid + 1][1]) / 2 if pn >= 2 else price_rows[0][1]

        liked_row = conn.execute(
            """
            SELECT
                SUM(COALESCE(rating_love,0) + COALESCE(rating_like,0)),
                SUM(COALESCE(rating_love,0) + COALESCE(rating_like,0)
                    + COALESCE(rating_ok,0) + COALESCE(rating_dislike,0) + COALESCE(rating_hate,0))
            FROM fragrances
            WHERE (rating_love + rating_like + rating_ok + rating_dislike + rating_hate) > 0
            """
        ).fetchone()
        mean_liked = (liked_row[0] / liked_row[1]) if liked_row and liked_row[1] else 0.7
        conn.close()
        return {
            "mean_rating": round(C, 4),
            "median_votes": m,
            "mean_price_value": round(C_price, 4),
            "median_price_votes": m_price,
            "mean_liked": round(mean_liked, 4),
        }

    # ---- Recommender feature matrix (global, over ALL frags) ----

    @cached_property
    def features(self) -> dict:
        """See frag-scraper `_compute_features`: dense 36-dim block + sparse
        note/accord/brand blocks, min-max scaled over the pool.

        Returns {"matrix": CSR (n_frags x d, float32), "ids": [frag ids aligned
        to rows], "pool_ids": frozenset of recommendable ids, "n_dense": int,
        "n_notes": int, "n_accords": int, "n_brands": int}.
        """
        g = self.globals
        C = g["mean_rating"]
        m = g["median_votes"]
        C_price = g["mean_price_value"]
        m_price = g["median_price_votes"]

        conn = self.conn()
        dense_rows = conn.execute(
            "SELECT id, rating, votes, year, in_production,"
            " COALESCE(rating_love,0), COALESCE(rating_like,0), COALESCE(rating_ok,0), COALESCE(rating_dislike,0), COALESCE(rating_hate,0),"
            " COALESCE(longevity_very_weak,0), COALESCE(longevity_weak,0), COALESCE(longevity_moderate,0), COALESCE(longevity_long_lasting,0), COALESCE(longevity_eternal,0),"
            " COALESCE(sillage_intimate,0), COALESCE(sillage_moderate,0), COALESCE(sillage_strong,0), COALESCE(sillage_enormous,0),"
            " COALESCE(gender_female,0), COALESCE(gender_more_female,0), COALESCE(gender_unisex,0), COALESCE(gender_more_male,0), COALESCE(gender_male,0),"
            " COALESCE(season_spring,0), COALESCE(season_summer,0), COALESCE(season_fall,0), COALESCE(season_winter,0),"
            " COALESCE(time_day,0), COALESCE(time_night,0),"
            " COALESCE(price_way_overpriced,0), COALESCE(price_overpriced,0), COALESCE(price_ok,0), COALESCE(price_good_value,0), COALESCE(price_great_value,0)"
            " FROM fragrances ORDER BY id"
        ).fetchall()
        note_rows = conn.execute(
            "SELECT id, top_notes_json, middle_notes_json, base_notes_json, accords_json, brand"
            " FROM fragrances ORDER BY id"
        ).fetchall()

        n = len(dense_rows)
        ids = [r[0] for r in dense_rows]
        D = np.zeros((n, N_DENSE), dtype=np.float64)
        pool_mask = np.zeros(n, dtype=bool)

        for i, r in enumerate(dense_rows):
            (fid, rating, votes, year, in_prod,
             love, like, ok, dislike, hate,
             lvw, lw, lmo, lll, let,
             si, smo, sst, se,
             gf, gmf, gu, gmm, gm,
             ssp, ssu, sfa, swi,
             td, tn,
             pow, po, pok, pgv, pgr) = r
            rating = rating or 0.0
            votes = votes or 0
            bayes = (C * m + rating * votes) / (m + votes) if votes else 0.0
            if votes >= REC_POOL_MIN_VOTES and bayes >= REC_POOL_MIN_BAYES:
                pool_mask[i] = True
            pt = pow + po + pok + pgv + pgr
            praw = (1.0 * pow + 2 * po + 3 * pok + 4 * pgv + 5 * pgr) / pt if pt else C_price
            pval = (C_price * m_price + praw * pt) / (m_price + pt) if pt else C_price
            D[i, 0:5] = _shares(love, like, ok, dislike, hate)
            D[i, 5:10] = _shares(lvw, lw, lmo, lll, let)
            D[i, 10:14] = _shares(si, smo, sst, se)
            D[i, 14:19] = _shares(gf, gmf, gu, gmm, gm)
            D[i, 19:23] = _shares(ssp, ssu, sfa, swi)
            D[i, 23:25] = _shares(td, tn)
            D[i, 25:30] = _shares(pow, po, pok, pgv, pgr)
            D[i, 30] = pval
            D[i, 31] = bayes
            D[i, 32] = rating
            D[i, 33] = math.log1p(votes) if votes else 0.0
            D[i, 34] = float(year or 0)
            D[i, 35] = 1.0 if in_prod == 1 else 0.0

        pool_ids = frozenset(ids[i] for i in np.flatnonzero(pool_mask).tolist())

        # Min-max scale dense features over the pool only.
        dmin = D[pool_mask].min(axis=0)
        dmax = D[pool_mask].max(axis=0)
        span = dmax - dmin
        span[span <= 1e-12] = 1.0
        D = np.clip((D - dmin) / span, 0.0, 1.0)

        # Note (layer, name) terms with pool document frequency >= REC_NOTE_MIN_DF.
        note_terms = [r[0] for r in conn.execute(
            "SELECT layer || char(31) || name AS term FROM ("
            " SELECT DISTINCT f.id, 'top' AS layer, json_extract(value,'$.name') AS name"
            " FROM fragrances f, json_each(f.top_notes_json)"
            " WHERE f.top_notes_json IS NOT NULL AND f.votes >= ?"
            " UNION ALL"
            " SELECT DISTINCT f.id, 'mid', json_extract(value,'$.name')"
            " FROM fragrances f, json_each(f.middle_notes_json)"
            " WHERE f.middle_notes_json IS NOT NULL AND f.votes >= ?"
            " UNION ALL"
            " SELECT DISTINCT f.id, 'base', json_extract(value,'$.name')"
            " FROM fragrances f, json_each(f.base_notes_json)"
            " WHERE f.base_notes_json IS NOT NULL AND f.votes >= ?"
            ") WHERE name IS NOT NULL GROUP BY term HAVING COUNT(*) >= ?",
            (REC_POOL_MIN_VOTES, REC_POOL_MIN_VOTES, REC_POOL_MIN_VOTES, REC_NOTE_MIN_DF),
        )]
        accord_terms = [r[0] for r in conn.execute(
            "SELECT DISTINCT json_extract(value,'$.name') FROM fragrances, json_each(accords_json)"
            " WHERE accords_json IS NOT NULL AND votes >= ?",
            (REC_POOL_MIN_VOTES,),
        )]
        top_brands = [r[0] for r in conn.execute(
            "SELECT brand FROM fragrances WHERE brand IS NOT NULL AND brand != ''"
            " GROUP BY brand ORDER BY COALESCE(SUM(votes),0) DESC, brand LIMIT 100"
        )]
        conn.close()

        note_vocab = sorted(
            {(t.split("\x1f", 1)[0], _norm_term(t.split("\x1f", 1)[1]))
             for t in note_terms if t.split("\x1f", 1)[1]}
        )
        accord_vocab = sorted({a for a in (_norm_term(a) for a in accord_terms) if a})
        brand_vocab = [b for b in (_norm_term(b) for b in top_brands) if b] if REC_USE_BRANDS else []
        n_notes, n_accords, n_brands = len(note_vocab), len(accord_vocab), len(brand_vocab)
        note_col = {k: i for i, k in enumerate(note_vocab)}
        accord_col = {k: n_notes + i for i, k in enumerate(accord_vocab)}
        brand_col = {b: n_notes + n_accords + i for i, b in enumerate(brand_vocab)} if REC_USE_BRANDS else {}

        rows_ix, cols_ix, data = [], [], []
        for i, (fid, top_j, mid_j, base_j, acc_j, brand) in enumerate(note_rows):
            for layer, j in (("top", top_j), ("mid", mid_j), ("base", base_j)):
                if not j:
                    continue
                try:
                    arr = json.loads(j)
                except (ValueError, TypeError):
                    arr = []
                for item in arr:
                    nm = _norm_term(item.get("name"))
                    if not nm:
                        continue
                    col = note_col.get((layer, nm))
                    if col is None:
                        continue
                    pct = item.get("strength_pct")
                    w = 100.0 if pct is None else float(pct)
                    rows_ix.append(i); cols_ix.append(col); data.append(w / 100.0)
            if acc_j:
                try:
                    arr = json.loads(acc_j)
                except (ValueError, TypeError):
                    arr = []
                for item in arr:
                    nm = _norm_term(item.get("name"))
                    if not nm:
                        continue
                    col = accord_col.get(nm)
                    if col is None:
                        continue
                    pct = item.get("strength_pct")
                    w = 100.0 if pct is None else float(pct)
                    rows_ix.append(i); cols_ix.append(col); data.append(w / 100.0)
            if REC_USE_BRANDS:
                bc = brand_col.get(_norm_term(brand))
                if bc is not None:
                    rows_ix.append(i); cols_ix.append(bc); data.append(1.0)

        d_sparse = n_notes + n_accords + n_brands
        S = sparse.csr_matrix((data, (rows_ix, cols_ix)), shape=(n, d_sparse), dtype=np.float64)
        if REC_SPARSE_NORM:
            lo, hi = 0, n_notes + n_accords
            B = S[:, lo:hi].copy()
            norms = np.sqrt(np.asarray(B.multiply(B).sum(axis=1)).ravel())
            norms[norms <= 1e-9] = 1.0
            B = sparse.diags(1.0 / norms) @ B
            S = sparse.hstack([S[:, :lo], B, S[:, hi:]], format="csr")
        M = sparse.hstack([sparse.csr_matrix(D), S], format="csr").astype(np.float32)
        return {
            "matrix": M,
            "ids": ids,
            "pool_ids": pool_ids,
            "n_dense": N_DENSE,
            "n_notes": n_notes,
            "n_accords": n_accords,
            "n_brands": n_brands,
        }

    def is_recommendable(self, frag_id: int) -> bool:
        """True if a fragrance is in the recommendable pool (20+ votes, 3.8+
        Bayesian). The pool is what the recommender and (future) Browse serve."""
        return frag_id in self.features["pool_ids"]

    # ---- Display hydration ----

    def fetch_info(self, ids, min_votes=0, min_rating=0, available=False) -> dict:
        """Fetch display + Bayesian-score info for a set of fragrance ids,
        returning {} for ids not found. Mirrors reference `_fetch_frag_info`."""
        g = self.globals
        C, m = g["mean_rating"], g["median_votes"]
        info = {}
        ids = list(ids)
        BATCH = 500
        for i in range(0, len(ids), BATCH):
            batch = ids[i:i + BATCH]
            placeholders = ",".join("?" * len(batch))
            extra_clauses, extra_params = [], []
            if min_votes > 0:
                extra_clauses.append("votes >= ?")
                extra_params.append(min_votes)
            if min_rating > 0:
                extra_clauses.append("(rating IS NOT NULL AND rating >= ?)")
                extra_params.append(min_rating)
            if available:
                extra_clauses.append("in_production = 1")
            extra_sql = " AND " + " AND ".join(extra_clauses) if extra_clauses else ""
            conn = self.conn()
            rows = conn.execute(
                f"SELECT id, name, brand, year, url, image_url, rating, votes,"
                f" rating_love, rating_like, rating_ok, rating_dislike, rating_hate"
                f" FROM fragrances WHERE id IN ({placeholders}){extra_sql}",
                batch + extra_params,
            ).fetchall()
            conn.close()
            for r in rows:
                rating = r["rating"] or 0
                votes = r["votes"] or 0
                bayes = (C * m + rating * votes) / (m + votes) if (m + votes) else 0
                love = r["rating_love"] or 0; like = r["rating_like"] or 0
                ok = r["rating_ok"] or 0; dislike = r["rating_dislike"] or 0; hate = r["rating_hate"] or 0
                total_sent = love + like + ok + dislike + hate
                loved = (2 * love + like - dislike - 2 * hate) / (total_sent + m) if (total_sent + m) else 0
                info[r["id"]] = {
                    "id": r["id"], "name": r["name"], "brand": r["brand"],
                    "year": r["year"], "url": r["url"], "image_url": r["image_url"],
                    "rating": r["rating"], "votes": r["votes"],
                    "bayesian_score": round(bayes, 4),
                    "most_loved_score": round(loved, 6),
                }
        return info

    def fragrance_full(self, frag_id: int) -> dict | None:
        """The full fragrance row (SELECT *), with note/accord JSON columns
        parsed into arrays, or None if the id isn't in the catalog."""
        conn = self.conn()
        row = conn.execute("SELECT * FROM fragrances WHERE id = ?", (frag_id,)).fetchone()
        conn.close()
        if row is None:
            return None
        data = dict(row)
        for col in ("top_notes_json", "middle_notes_json", "base_notes_json", "accords_json"):
            val = data.get(col)
            if isinstance(val, str):
                try:
                    data[col] = json.loads(val)
                except (ValueError, TypeError):
                    data[col] = []
        return data


# Module singleton. Consumers reference it via the module (`from app import catalog
# as cat; cat.catalog`) so tests can swap it (monkeypatch app.catalog.catalog).
catalog = Catalog(get_settings().catalog_db)