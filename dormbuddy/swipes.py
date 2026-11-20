from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .matching import compare
from .models import Match, Profile, Swipe
from .profiles import PROFILES_WITH_PREFERENCES, questionnaire
from .web import DB, CurrentUser, Form, redirect, render

router = APIRouter()
RecordId = Annotated[int, Path(ge=1, le=2_147_483_647)]


def save_swipe(db: Session, actor_id: int, target_id: int, action: str) -> bool:
    if actor_id == target_id or action not in {"like", "skip"}:
        raise HTTPException(400, "Нельзя выполнить это действие.")
    first_id, second_id = sorted((actor_id, target_id))
    # Both directions share the lock. The next statement sees a committed reverse swipe.
    db.execute(select(func.pg_advisory_xact_lock(first_id, second_id)))
    swipe = db.get(Swipe, (actor_id, target_id))
    if swipe is None:
        profiles = {
            profile.user_id: profile
            for profile in db.scalars(PROFILES_WITH_PREFERENCES.where(Profile.user_id.in_([actor_id, target_id])))
        }
        if target_id not in profiles or compare(questionnaire(profiles[actor_id]), questionnaire(profiles[target_id])) is None:
            raise HTTPException(404)
        swipe = Swipe(actor_id=actor_id, target_id=target_id, action=action)
        db.add(swipe)

    reverse = db.get(Swipe, (target_id, actor_id)) if swipe.action == "like" else None
    matched = reverse is not None and reverse.action == "like"
    if matched:
        db.execute(
            insert(Match).values(first_id=first_id, second_id=second_id)
            .on_conflict_do_nothing(index_elements=[Match.first_id, Match.second_id])
        )
    db.commit()
    return matched


@router.post("/neighbors/{target_id}/swipe")
def swipe_neighbor(target_id: RecordId, db: DB, user: CurrentUser, form: Form):
    matched = save_swipe(db, user.id, target_id, form.get("action", ""))
    return redirect("/neighbors?matched=1" if matched else "/neighbors")


def membership(user_id: int):
    return or_(Match.first_id == user_id, Match.second_id == user_id)


@router.get("/matches")
def matches(request: Request, db: DB, user: CurrentUser):
    matches = db.scalars(select(Match).where(membership(user.id)).order_by(Match.id.desc())).all()
    matching_ids = {match.id: match.second_id if match.first_id == user.id else match.first_id for match in matches}
    names = dict(db.execute(select(Profile.user_id, Profile.display_name).where(
        Profile.user_id.in_(matching_ids.values())
    )).all()) if matches else {}
    return render(
        request, "matches.html", user=user,
        matches=[(match.id, names[matching_ids[match.id]]) for match in matches],
    )
