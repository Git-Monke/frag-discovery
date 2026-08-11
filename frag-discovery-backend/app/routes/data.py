"""Per-user data routes: favorites, feedback, recommend, and fragrance detail.

Only `/api/fragrance/<id>` is public (optional auth, for the per-user `favorited`
flag). The rest are scoped to the signed-in user via `get_current_session`.
"""

from datetime import UTC, datetime

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from app import catalog as catalog_mod
from app import recommender
from app.auth.dependencies import get_current_session, get_optional_user
from app.db import get_db
from app.models import Favorite, User, UserFeedback
from app.models import Session as SessionModel
from app.schemas import FeedbackBody

router = APIRouter()


def _now() -> datetime:
    return datetime.now(UTC)


# ---- Favorites ----

@router.get("/favorites")
def list_favorites(
    sort: str = "recent",
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    if sort not in ("recent", "recommend"):
        sort = "recent"
    catalog = catalog_mod.catalog

    fav_rows = (
        db.query(Favorite)
        .filter(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    info = catalog.fetch_info([f.frag_id for f in fav_rows])
    results = []
    for f in fav_rows:
        d = info.get(f.frag_id)
        if not d:
            continue
        d["favorited"] = True
        d["p"] = None
        results.append(d)

    fb_rows = db.query(UserFeedback).filter(UserFeedback.user_id == user.id).all()
    counts = recommender._feedback_counts(fb_rows)
    n_favs = len(results)
    meta = {
        "trained": n_favs + counts["interested"] >= recommender.REC_MIN_FAVORITES,
        "favorites": n_favs,
        "levels": counts,
        "sort": sort,
    }

    if sort == "recommend":
        fav_ids = {f.frag_id for f in fav_rows}
        model = recommender.get_model(db, user.id)
        meta["favorites"] = len(fav_ids)
        meta["trained"] = model is not None
        if model is not None:
            F = catalog.features
            id_row = {fid: i for i, fid in enumerate(F["ids"])}
            scored = [d for d in results if d["id"] in id_row]
            ix = [id_row[d["id"]] for d in scored]
            if ix:
                probs = model.predict_proba(F["matrix"][np.array(ix, dtype=np.int64)])
                for d, p in zip(scored, probs):
                    d["p"] = round(float(p), 4)
            meta["trained"] = True
        # Highest P(favorite) first; unscorable rows (p=null) go last.
        results.sort(key=lambda d: (d["p"] is None, -(d["p"] if d["p"] is not None else 0.0)))

    return {"count": len(results), "results": results, "recommender": meta}


@router.delete("/favorites")
def clear_favorites(
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    db.query(Favorite).filter(Favorite.user_id == user.id).delete()
    # Clear love signals so the recommender isn't trained on vanished favs.
    db.query(UserFeedback).filter(
        UserFeedback.user_id == user.id, UserFeedback.action == "love"
    ).delete()
    db.commit()
    return {"count": 0}


@router.post("/favorites/{frag_id}")
def add_favorite(
    frag_id: int,
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    if not (
        db.query(Favorite)
        .filter(Favorite.user_id == user.id, Favorite.frag_id == frag_id)
        .first()
    ):
        db.add(Favorite(user_id=user.id, frag_id=frag_id))
    # Favoriting == loving: log it as a strong positive training signal too.
    row = (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == user.id, UserFeedback.frag_id == frag_id)
        .first()
    )
    if row:
        row.action = "love"
        row.weight = recommender.FEEDBACK_WEIGHTS["love"]
        row.created_at = _now()
    else:
        db.add(
            UserFeedback(
                user_id=user.id, frag_id=frag_id,
                action="love", weight=recommender.FEEDBACK_WEIGHTS["love"],
            )
        )
    db.commit()
    return {"favorited": True}


@router.delete("/favorites/{frag_id}")
def remove_favorite(
    frag_id: int,
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    db.query(Favorite).filter(
        Favorite.user_id == user.id, Favorite.frag_id == frag_id
    ).delete()
    # Un-favoriting revokes the love signal (keep any other rating).
    db.query(UserFeedback).filter(
        UserFeedback.user_id == user.id,
        UserFeedback.frag_id == frag_id,
        UserFeedback.action == "love",
    ).delete()
    db.commit()
    return {"favorited": False}


# ---- Feedback (taste ratings that train the recommender) ----

@router.post("/feedback/{frag_id}")
def post_feedback(
    frag_id: int,
    body: FeedbackBody,
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    action = body.action
    if action in recommender.LEGACY_FEEDBACK:
        action = recommender.LEGACY_FEEDBACK[action]
    if action not in recommender.FEEDBACK_WEIGHTS:
        raise HTTPException(status_code=400, detail="invalid action")
    weight = recommender.FEEDBACK_WEIGHTS[action]

    row = (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == user.id, UserFeedback.frag_id == frag_id)
        .first()
    )
    if row:
        row.action = action
        row.weight = weight
        row.created_at = _now()
    else:
        db.add(UserFeedback(user_id=user.id, frag_id=frag_id, action=action, weight=weight))

    if action == "love" and not (
        db.query(Favorite)
        .filter(Favorite.user_id == user.id, Favorite.frag_id == frag_id)
        .first()
    ):
        # Love is the favorite signal — keep the two tables in sync.
        db.add(Favorite(user_id=user.id, frag_id=frag_id))
    db.commit()
    return {"ok": True}


@router.delete("/feedback/{frag_id}")
def delete_feedback(
    frag_id: int,
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    row = (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == user.id, UserFeedback.frag_id == frag_id)
        .first()
    )
    if row:
        action = row.action
        db.delete(row)
        if action == "love":
            # Removing a love also removes the favorite.
            db.query(Favorite).filter(
                Favorite.user_id == user.id, Favorite.frag_id == frag_id
            ).delete()
        db.commit()
    return {"ok": True}


# ---- Recommend (personalized Discover feed) ----

@router.get("/recommend")
def recommend(
    limit: int = 12,
    db: OrmSession = Depends(get_db),
    auth: tuple[User, SessionModel] = Depends(get_current_session),
) -> dict:
    user, _ = auth
    limit = max(1, min(100, limit))
    return recommender.recommend_batch(db, user.id, limit)


# ---- Fragrance detail (public; per-user favorited flag when signed in) ----

@router.get("/fragrance/{frag_id}")
def get_fragrance(
    frag_id: int,
    db: OrmSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    data = catalog_mod.catalog.fragrance_full(frag_id)
    if data is None:
        raise HTTPException(status_code=404, detail="not found")
    data["favorited"] = False
    if user is not None:
        data["favorited"] = (
            db.query(Favorite)
            .filter(Favorite.user_id == user.id, Favorite.frag_id == frag_id)
            .first()
            is not None
        )
    return data
