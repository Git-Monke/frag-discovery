"""Browse query building: filters + derived score columns.

Port of frag-scraper/app.py `build_query` + `_build_condition_sql` (+ the
filter constants). The SELECT carries the derived score expressions (Bayesian,
price-value, love-per-dollar, most-loved, most-liked, controversial) and all
the vote-bucket columns the frontend's `FragranceRow` expects.

**Pool restriction (locked decision):** Browse only surfaces the recommendable
pool — `votes >= REC_POOL_MIN_VOTES` AND a Bayesian rating `>= REC_POOL_MIN_BAYES`
— the same set the feature matrix / recommender are built over. Applied to ALL
sorts (including the Bayesian fallback), unlike the reference which only added
`votes >= 20` for the recommended sort.
"""

import json
from dataclasses import dataclass, field

from app import catalog as catalog_mod
from app.catalog import REC_POOL_MIN_BAYES, REC_POOL_MIN_VOTES

# ---- Vote-group columns (dominant-bucket filters) ----

VOTE_GROUPS = {
    "longevity": [
        "longevity_very_weak", "longevity_weak", "longevity_moderate",
        "longevity_long_lasting", "longevity_eternal",
    ],
    "sillage": [
        "sillage_intimate", "sillage_moderate", "sillage_strong", "sillage_enormous",
    ],
    "season": [
        "season_spring", "season_summer", "season_fall", "season_winter",
    ],
    "gender": [
        "gender_female", "gender_more_female", "gender_unisex",
        "gender_more_male", "gender_male",
    ],
}
VALID_COLS = {col for cols in VOTE_GROUPS.values() for col in cols}

LONGEVITY_ORDER = ["longevity_very_weak", "longevity_weak", "longevity_moderate",
                   "longevity_long_lasting", "longevity_eternal"]
SILLAGE_ORDER = ["sillage_intimate", "sillage_moderate", "sillage_strong", "sillage_enormous"]

SORT_MAP = {
    "bayesian":        "bayesian_score",
    "rating":          "rating",
    "votes":           "votes",
    "loved":           "most_loved_score",
    "liked":           "most_liked_score",
    "controversial":   "controversial_score",
    "price_value":     "price_value_score",
    "love_per_dollar": "love_per_dollar_score",
    "year":            "year",
    "name":            "name",
}


def min_threshold_sql(full_col: str, ordered: list[str]) -> str | None:
    """`longevity_min` / `sillage_min` semantics: the selected bucket + every
    stronger bucket combined must out-vote everything below it."""
    s = lambda c: f"COALESCE({c},0)"
    idx = ordered.index(full_col)
    above = [s(c) for c in ordered[idx:]]
    below = [s(c) for c in ordered[:idx]]
    if not below:
        return None  # already the minimum category — no constraint needed
    return f"{'+'.join(above)} > {'+'.join(below)}"


def build_condition_sql(cond: dict) -> tuple[str, list] | None:
    """Return (sql_fragment, params) for one note/accord condition, or None if
    invalid. Port of frag-scraper `_build_condition_sql`."""
    ctype = cond.get("type", "")

    if ctype == "at_least":
        names = [n.strip() for n in cond.get("names", []) if n.strip()]
        count = max(1, int(cond.get("count", 1)))
        if not names:
            return None
        all_cols = ["top_notes_json", "middle_notes_json", "base_notes_json", "accords_json"]
        terms, p = [], []
        for name in names:
            pattern = f"%{name.lower()}%"
            sub = []
            for col in all_cols:
                sub.append(
                    f"EXISTS (SELECT 1 FROM json_each({col}) WHERE {col} IS NOT NULL"
                    f" AND lower(json_extract(value,'$.name')) LIKE ?)"
                )
                p.append(pattern)
            terms.append(f"({' OR '.join(sub)})")
        return f"({' + '.join(terms)}) >= {count}", p

    name = cond.get("name", "").strip()
    if not name:
        return None

    min_pct = cond.get("min_pct")
    max_pct = cond.get("max_pct")
    # upper_only means "absent or below threshold" semantics.
    upper_only = max_pct is not None and min_pct is None
    name_pattern = f"%{name}%"

    def strength_clauses(min_p, max_p):
        clauses, p = [], []
        if min_p is not None and max_p is not None:
            clauses.append("json_extract(value,'$.strength_pct') BETWEEN ? AND ?")
            p += [float(min_p), float(max_p)]
        elif min_p is not None:
            clauses.append("json_extract(value,'$.strength_pct') >= ?")
            p.append(float(min_p))
        elif max_p is not None:
            clauses.append("json_extract(value,'$.strength_pct') <= ?")
            p.append(float(max_p))
        return clauses, p

    def exists_in(json_col):
        s_clauses, s_params = strength_clauses(min_pct, max_pct)
        where = " AND ".join(["lower(json_extract(value,'$.name')) LIKE ?"] + s_clauses)
        return f"SELECT 1 FROM json_each({json_col}) WHERE {where}", [name_pattern] + s_params

    if ctype == "accord":
        if upper_only:
            absent = (
                "SELECT 1 FROM json_each(accords_json)"
                " WHERE lower(json_extract(value,'$.name')) LIKE ?"
            )
            e_sql, e_p = exists_in("accords_json")
            return f"(NOT EXISTS ({absent}) OR EXISTS ({e_sql}))", [name_pattern] + e_p
        e_sql, e_p = exists_in("accords_json")
        return f"EXISTS ({e_sql})", e_p

    note_cols_map = {
        "top":      ["top_notes_json"],
        "mid":      ["middle_notes_json"],
        "base":     ["base_notes_json"],
        "any_note": ["top_notes_json", "middle_notes_json", "base_notes_json"],
    }
    cols = note_cols_map.get(ctype)
    if not cols:
        return None

    if upper_only:
        absent_parts = [
            f"NOT EXISTS (SELECT 1 FROM json_each({col})"
            f" WHERE lower(json_extract(value,'$.name')) LIKE ?)"
            for col in cols
        ]
        absent_params = [name_pattern] * len(cols)
        exists_parts, exists_params = [], []
        for col in cols:
            e_sql, e_p = exists_in(col)
            exists_parts.append(f"EXISTS ({e_sql})")
            exists_params += e_p
        sql = f"(({' AND '.join(absent_parts)}) OR ({' OR '.join(exists_parts)}))"
        return sql, absent_params + exists_params

    parts, all_params = [], []
    for col in cols:
        e_sql, e_p = exists_in(col)
        parts.append(f"EXISTS ({e_sql})")
        all_params += e_p
    return "(" + " OR ".join(parts) + ")", all_params


@dataclass
class QuerySpec:
    count_sql: str
    data_sql: str | None      # full-row ORDER BY ... LIMIT/OFFSET (non-reco path)
    ids_sql: str | None       # id-only query (reco path)
    select_sql: str           # SELECT ... FROM fragrances (no where/order)
    params: list = field(default_factory=list)
    page: int = 1
    page_size: int = 25
    is_reco: bool = False
    sort_col: str = "bayesian_score"
    order: str = "desc"


def build_query(args: dict) -> QuerySpec:
    """Build the SQL for a browse/search request. `args` is a dict of raw
    string query params (mirrors the reference handler)."""
    g = catalog_mod.catalog.globals
    C = g["mean_rating"]
    m = g["median_votes"]
    C_price = g["mean_price_value"]
    m_price = g["median_price_votes"]
    C_liked = g["mean_liked"]

    # Sentiment score expressions (mirror the reference SELECT verbatim).
    total_sent = ("(COALESCE(rating_love,0)+COALESCE(rating_like,0)+COALESCE(rating_ok,0)"
                  "+COALESCE(rating_dislike,0)+COALESCE(rating_hate,0))")
    most_loved_expr = (
        f"(2.0*COALESCE(rating_love,0) + COALESCE(rating_like,0)"
        f" - COALESCE(rating_dislike,0) - 2.0*COALESCE(rating_hate,0))"
        f" / NULLIF({total_sent} + {m}, 0)"
    )
    friendly_expr = (
        f"CAST(COALESCE(rating_love,0)+COALESCE(rating_like,0) AS REAL)"
        f" / NULLIF({total_sent}+{m},0)"
    )
    controversial_expr = (
        f"2.0 * MIN("
        f"  CAST(COALESCE(rating_love,0)+COALESCE(rating_like,0) AS REAL) / NULLIF({total_sent},0),"
        f"  CAST(COALESCE(rating_dislike,0)+COALESCE(rating_hate,0) AS REAL) / NULLIF({total_sent},0)"
        f")"
    )
    _pt = ("(COALESCE(price_way_overpriced,0)+COALESCE(price_overpriced,0)"
           "+COALESCE(price_ok,0)+COALESCE(price_good_value,0)+COALESCE(price_great_value,0))")
    _praw = (f"(1.0*COALESCE(price_way_overpriced,0)+2*COALESCE(price_overpriced,0)"
             f"+3*COALESCE(price_ok,0)+4*COALESCE(price_good_value,0)"
             f"+5*COALESCE(price_great_value,0)) / NULLIF({_pt},0)")
    price_value_expr = f"({C_price} * {m_price} + ({_praw}) * {_pt}) / ({m_price} + {_pt})"
    love_per_dollar_expr = f"({friendly_expr}) / NULLIF(6.0 - ({price_value_expr}), 0)"
    most_liked_expr = (
        f"(CAST(COALESCE(rating_love,0)+COALESCE(rating_like,0) AS REAL) + {m} * {C_liked})"
        f" / ({total_sent} + {m})"
    )

    select = f"""
        SELECT
            id, name, brand, year, url, rating, votes, image_url,
            ({C} * {m} + COALESCE(rating,0) * COALESCE(votes,0)) / ({m} + COALESCE(votes,0)) AS bayesian_score,
            {price_value_expr} AS price_value_score,
            {love_per_dollar_expr} AS love_per_dollar_score,
            {most_loved_expr} AS most_loved_score,
            {most_liked_expr} AS most_liked_score,
            {controversial_expr} AS controversial_score,
            longevity_very_weak, longevity_weak, longevity_moderate, longevity_long_lasting, longevity_eternal,
            sillage_intimate, sillage_moderate, sillage_strong, sillage_enormous,
            season_spring, season_summer, season_fall, season_winter,
            gender_female, gender_more_female, gender_unisex, gender_more_male, gender_male,
            rating_love, rating_like, rating_ok, rating_dislike, rating_hate,
            time_day, time_night,
            price_way_overpriced, price_overpriced, price_ok, price_good_value, price_great_value
        FROM fragrances
    """

    wheres, params = [], []

    q = args.get("q", "").strip()
    if q:
        wheres.append("(name LIKE ? OR brand LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    brand = args.get("brand", "").strip()
    if brand:
        wheres.append("brand = ?")
        params.append(brand)

    for key, col_name in [("year_min", "year >="), ("year_max", "year <=")]:
        try:
            val = int(args.get(key, ""))
            op = col_name.split()[1]
            field_name = col_name.split()[0]
            wheres.append(f"{field_name} {op} ?")
            params.append(val)
        except (ValueError, TypeError):
            pass

    for key, expr in [("rating_min", "rating >= ?"), ("rating_max", "rating <= ?")]:
        try:
            val = float(args.get(key, ""))
            wheres.append(expr)
            params.append(val)
        except (ValueError, TypeError):
            pass

    for key, expr in [("votes_min", "votes >= ?"), ("votes_max", "votes <= ?")]:
        try:
            val = int(args.get(key, ""))
            wheres.append(expr)
            params.append(val)
        except (ValueError, TypeError):
            pass

    _gender_param = args.get("gender", "").strip()
    _s = lambda c: f"COALESCE({c},0)"
    if _gender_param == "male_wearable":
        wheres.append(
            f"{_s('gender_unisex')}+{_s('gender_more_male')}+{_s('gender_male')}"
            f" > {_s('gender_female')}+{_s('gender_more_female')}"
        )
    elif _gender_param == "female_wearable":
        wheres.append(
            f"{_s('gender_female')}+{_s('gender_more_female')}+{_s('gender_unisex')}"
            f" > {_s('gender_male')}+{_s('gender_more_male')}"
        )

    _season_param = args.get("season", "").strip()
    _season_total = f"NULLIF({_s('season_spring')}+{_s('season_summer')}+{_s('season_fall')}+{_s('season_winter')},0)"
    _time_total = f"NULLIF({_s('time_day')}+{_s('time_night')},0)"
    if _season_param == "hot":
        wheres.append(f"{_s('season_spring')}+{_s('season_summer')} > {_s('season_fall')}+{_s('season_winter')}")
    elif _season_param == "cold":
        wheres.append(f"{_s('season_fall')}+{_s('season_winter')} > {_s('season_spring')}+{_s('season_summer')}")
    elif _season_param == "universal":
        wheres.append(
            f"CAST({_s('season_spring')} AS REAL)/{_season_total} >= 0.20"
            f" AND CAST({_s('season_summer')} AS REAL)/{_season_total} >= 0.20"
            f" AND CAST({_s('season_fall')}   AS REAL)/{_season_total} >= 0.20"
            f" AND CAST({_s('season_winter')} AS REAL)/{_season_total} >= 0.20"
            f" AND CAST({_s('time_day')}   AS REAL)/{_time_total} >= 0.40"
            f" AND CAST({_s('time_night')} AS REAL)/{_time_total} >= 0.40"
        )

    _longevity_min = args.get("longevity_min", "").strip() == "1"
    _sillage_min = args.get("sillage_min", "").strip() == "1"

    for group_name, cols in VOTE_GROUPS.items():
        selected = args.get(group_name, "").strip()
        if not selected:
            continue
        if group_name == "season" and _season_param in ("hot", "cold", "universal"):
            continue
        if group_name == "gender" and _gender_param in ("male_wearable", "female_wearable"):
            continue
        full_col = f"{group_name}_{selected}"
        if full_col not in VALID_COLS:
            continue
        if group_name == "longevity" and _longevity_min:
            sql = min_threshold_sql(full_col, LONGEVITY_ORDER)
            if sql:
                wheres.append(sql)
            continue
        if group_name == "sillage" and _sillage_min:
            sql = min_threshold_sql(full_col, SILLAGE_ORDER)
            if sql:
                wheres.append(sql)
            continue
        coalesced = [f"COALESCE({c},0)" for c in cols]
        wheres.append(
            f"COALESCE({full_col},0) = MAX({', '.join(coalesced)}) AND {full_col} > 0"
        )

    if args.get("available", "").strip() == "1":
        wheres.append("in_production = 1")

    conditions_raw = args.get("conditions", "")
    if conditions_raw:
        try:
            conditions = json.loads(conditions_raw)
        except (ValueError, TypeError):
            conditions = []
        for cond in conditions:
            result = build_condition_sql(cond)
            if result:
                sql_frag, cond_params = result
                wheres.append(sql_frag)
                params += cond_params

    # Pool restriction (locked decision): Browse models the recommendable pool —
    # the same frags the feature matrix / recommender are built over. Applied to
    # every sort so the Bayesian fallback also stays on the pool.
    wheres.append(
        f"votes >= {REC_POOL_MIN_VOTES}"
        f" AND ({C} * {m} + COALESCE(rating,0) * COALESCE(votes,0))"
        f" / ({m} + COALESCE(votes,0)) >= {REC_POOL_MIN_BAYES}"
    )

    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    is_reco = args.get("sort") == "recommended"
    sort_col = SORT_MAP.get(args.get("sort", "bayesian"), "bayesian_score")
    order = "ASC" if args.get("order", "desc") == "asc" else "DESC"

    try:
        page = max(1, int(args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = min(100, max(1, int(args.get("page_size", 25))))
    except (ValueError, TypeError):
        page_size = 25
    offset = (page - 1) * page_size

    count_sql = f"SELECT COUNT(*) FROM fragrances {where_clause}"
    if is_reco:
        # Model-scored in the route: return every candidate id, no ORDER/LIMIT.
        data_sql = None
        ids_sql = f"SELECT id FROM fragrances {where_clause}"
    else:
        data_sql = (
            f"{select} {where_clause} ORDER BY {sort_col} {order} NULLS LAST"
            f" LIMIT {page_size} OFFSET {offset}"
        )
        ids_sql = None
    return QuerySpec(
        count_sql=count_sql,
        data_sql=data_sql,
        ids_sql=ids_sql,
        select_sql=select,
        params=params,
        page=page,
        page_size=page_size,
        is_reco=is_reco,
        sort_col=sort_col,
        order=order,
    )
