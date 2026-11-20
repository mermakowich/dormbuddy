from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from .matching import PREFERENCE_FIELDS, REQUIRED_ANSWERS, SCALES, SLEEP, Questionnaire
from .models import Dormitory, Profile, University
from .web import DB, CurrentUser, Form, read_int, redirect, render

router = APIRouter()
HABITS = {
    "smokes": "Я курю",
    "allows_smoking": "Допускаю курение соседа",
    "has_pet": "У меня есть питомец",
    "allows_pets": "Допускаю питомцев соседа",
}
MOVE_STAGES = {
    "planning": "Планирую переезд",
    "packing": "Готовлюсь к переезду",
    "settling": "Уже переехал(а)",
}
PROFILE_FIELDS = (
    "display_name", "mode", "district", "budget_min", "budget_max", "university_id",
    "dormitory_id", "dorm_scope", *REQUIRED_ANSWERS, "interests", "move_stage",
)
PROFILES_WITH_PREFERENCES = select(Profile).options(
    joinedload(Profile.preferences), joinedload(Profile.university), joinedload(Profile.dormitory)
)


def questionnaire(profile: Profile) -> Questionnaire:
    return Questionnaire(
        user_id=profile.user_id,
        display_name=profile.display_name,
        mode=profile.mode,
        university_id=profile.university_id,
        dormitory_id=profile.dormitory_id,
        dorm_scope=profile.dorm_scope,
        budget_min=profile.budget_min,
        budget_max=profile.budget_max,
        **{key: getattr(profile, key) for key in REQUIRED_ANSWERS},
        preferences={key: getattr(profile.preferences, key) for key in PREFERENCE_FIELDS},
    )


def form_values(profile: Profile):
    values = {key: getattr(profile, key) for key in PROFILE_FIELDS}
    for key in HABITS:
        values[key] = {None: "", True: "yes", False: "no"}[values[key]]
    values.update({key: getattr(profile.preferences, key) for key in PREFERENCE_FIELDS})
    return {key: str(value) if value is not None else "" for key, value in values.items()}


def profile_page(request, db, user, values, errors=None):
    universities = db.scalars(
        select(University).options(selectinload(University.dormitories)).order_by(University.name)
    ).all()
    return render(
        request, "profile.html", user=user, status=422 if errors else 200,
        values=values, universities=universities, errors=errors or {}, habits=HABITS,
        university_choices=[(item.id, item.name) for item in universities],
        scale_choices={key: list(enumerate(options, 1)) for key, (_, options) in SCALES.items()},
        sleep=SLEEP, scales=SCALES, move_stages=MOVE_STAGES,
        saved=request.query_params.get("saved") == "1" and not errors,
    )


@router.get("/profile")
@router.get("/dormitory")
def view_profile(request: Request, db: DB, user: CurrentUser):
    values = form_values(user.profile)
    if request.url.path == "/dormitory":
        values["mode"] = "dorm"
    elif request.query_params.get("mode") == "rent":
        values["mode"] = "rent"
    return profile_page(request, db, user, values)


@router.post("/profile")
def save_profile(request: Request, db: DB, user: CurrentUser, form: Form):
    keys = (*PROFILE_FIELDS, *PREFERENCE_FIELDS)
    values = {key: form.get(key, "").strip() for key in keys}
    errors = {}
    updates = {}
    for key, limit, label in [
        ("display_name", 80, "Имя"), ("district", 80, "Район"), ("interests", 240, "Интересы"),
    ]:
        if len(values[key]) > limit:
            errors[key] = f"{label} — до {limit} символов."
        updates[key] = values[key] or None
    if not updates["display_name"]:
        errors["display_name"] = "Укажи имя, которое увидят другие студенты."
    if values["mode"] not in {"rent", "dorm"}:
        errors["mode"] = "Выбери аренду или общежитие."
    updates["mode"] = values["mode"]
    updates["dorm_scope"] = values["dorm_scope"] or "dormitory"
    if updates["dorm_scope"] not in {"dormitory", "university"}:
        errors["dorm_scope"] = "Выбери, где искать соседей."
    updates["move_stage"] = values["move_stage"] or None
    if updates["move_stage"] and updates["move_stage"] not in MOVE_STAGES:
        errors["move_stage"] = "Выбери этап из списка."

    maximum_id = 2_147_483_647
    university_id = read_int(values, "university_id", 1, maximum_id, errors, "Выбери вуз из списка.")
    if university_id and db.get(University, university_id) is None:
        errors["university_id"] = "Выбранный вуз отсутствует в справочнике."
    updates.update(university_id=university_id, dormitory_id=None, budget_min=None, budget_max=None)
    if updates["mode"] == "dorm":
        updates["district"] = None
        if not university_id:
            errors.setdefault("university_id", "Выбери вуз.")
        dormitory_id = read_int(values, "dormitory_id", 1, maximum_id, errors, "Выбери общежитие из списка.")
        dormitory = db.get(Dormitory, dormitory_id) if dormitory_id else None
        if dormitory is None or dormitory.university_id != university_id:
            errors["dormitory_id"] = "Выбери общежитие этого вуза."
        updates["dormitory_id"] = dormitory_id
    elif updates["mode"] == "rent":
        for key in ("budget_min", "budget_max"):
            updates[key] = read_int(values, key, 1, 1_000_000, errors, "Укажи целую сумму от 1 до 1 000 000 ₽.")
        minimum, maximum = updates["budget_min"], updates["budget_max"]
        if (minimum is None) != (maximum is None):
            errors.setdefault("budget_min" if minimum is None else "budget_max", "Укажи обе границы бюджета.")
        if minimum is not None and maximum is not None and minimum > maximum:
            errors["budget_max"] = "Верхняя граница должна быть не меньше нижней."

    for key in HABITS:
        if values[key] not in {"yes", "no", ""}:
            errors[key] = "Выбери «Да», «Нет» или оставь без ответа."
        updates[key] = {"yes": True, "no": False}.get(values[key])
    sleep = values["sleep"] or None
    if sleep and sleep not in SLEEP:
        errors["sleep"] = "Выбери один из предложенных вариантов."
    preferences = {"sleep": sleep}
    for key in SCALES:
        preferences[key] = read_int(values, key, 1, 5, errors, "Выбери вариант из списка.")
    if errors:
        return profile_page(request, db, user, values, errors)
    for key, value in updates.items():
        setattr(user.profile, key, value)
    for key, value in preferences.items():
        setattr(user.profile.preferences, key, value)
    db.commit()
    return redirect("/profile?saved=1")
