from fastapi import APIRouter, Request
from sqlalchemy import select

from .matching import PREFERENCE_FIELDS, rank, ready
from .models import Profile, Swipe
from .profiles import PROFILES_WITH_PREFERENCES, questionnaire
from .web import DB, CurrentUser, render

router = APIRouter()


@router.get("/neighbors")
def neighbors(request: Request, db: DB, user: CurrentUser):
    profile = user.profile
    own = questionnaire(profile)
    complete = ready(own)
    recommendation = candidate = None
    if complete:
        handled = select(Swipe.target_id).where(Swipe.actor_id == user.id)
        candidates = db.scalars(PROFILES_WITH_PREFERENCES.where(
            Profile.user_id != user.id, Profile.user_id.not_in(handled), Profile.mode == profile.mode,
        )).all()
        by_id = {candidate.user_id: candidate for candidate in candidates}
        recommendations = rank(own, map(questionnaire, candidates))
        if recommendations:
            recommendation = recommendations[0]
            candidate = by_id[recommendation.candidate_id]
    return render(
        request, "neighbors.html", user=user, profile=profile, ready=complete,
        recommendation=recommendation, candidate=candidate, preference_count=len(PREFERENCE_FIELDS),
        matched=request.query_params.get("matched") == "1",
    )
