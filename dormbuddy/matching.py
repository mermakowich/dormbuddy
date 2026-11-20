"""Pure roommate compatibility rules shared by the feed and swipe validation."""

from dataclasses import dataclass, field
from fractions import Fraction

SLEEP = {"early": "Рано ложусь", "flexible": "Гибкий график", "late": "Поздно ложусь"}
SCALES = {
    "cleaning": ("Уборка", ("По необходимости", "Редко", "Еженедельно", "Несколько раз в неделю", "Ежедневно")),
    "guests": ("Гости", ("Почти никогда", "Редко", "Иногда", "Часто", "Очень часто")),
    "noise": ("Шум", ("Нужна тишина", "Предпочитаю тишину", "Зависит от времени", "Обычно не мешает", "Спокойно отношусь")),
    "cooking": ("Готовка", ("Почти не готовлю", "Редко", "Иногда", "Часто", "Каждый день")),
    "sociability": ("Общение", ("Люблю уединение", "Чаще по своим делам", "По настроению", "Люблю общаться", "Люблю проводить время вместе")),
}
PREFERENCE_FIELDS = ("sleep", *SCALES)
REQUIRED_ANSWERS = ("smokes", "allows_smoking", "has_pet", "allows_pets")


@dataclass(frozen=True)
class Questionnaire:
    user_id: int
    display_name: str = ""
    mode: str = "rent"
    university_id: int | None = None
    dormitory_id: int | None = None
    dorm_scope: str = "dormitory"
    budget_min: int | None = None
    budget_max: int | None = None
    smokes: bool | None = None
    allows_smoking: bool | None = None
    has_pet: bool | None = None
    allows_pets: bool | None = None
    preferences: dict[str, str | int | None] = field(default_factory=dict)


@dataclass(frozen=True)
class Comparison:
    label: str
    own: str
    other: str
    similarity: Fraction


@dataclass(frozen=True)
class Recommendation:
    candidate_id: int
    score: Fraction | None
    comparisons: tuple[Comparison, ...]
    conditions: tuple[str, ...]

    @property
    def display_score(self):
        return round(self.score) if self.score is not None else None


def ready(person: Questionnaire) -> bool:
    if not person.display_name or any(getattr(person, key) is None for key in REQUIRED_ANSWERS):
        return False
    if person.mode == "rent":
        return person.budget_min is not None and person.budget_max is not None
    return person.university_id is not None and person.dormitory_id is not None


def accepts(person: Questionnaire, candidate: Questionnaire) -> bool:
    if candidate.smokes and not person.allows_smoking or candidate.has_pet and not person.allows_pets:
        return False
    if person.mode == "dorm":
        return person.university_id == candidate.university_id and (
            person.dorm_scope == "university" or person.dormitory_id == candidate.dormitory_id
        )
    return candidate.budget_min <= person.budget_max and person.budget_min <= candidate.budget_max


def compare_preferences(left: Questionnaire, right: Questionnaire) -> tuple[Comparison, ...]:
    result = []
    for key in PREFERENCE_FIELDS:
        own, other = left.preferences.get(key), right.preferences.get(key)
        if own is None or other is None:
            continue
        if key == "sleep":
            result.append(Comparison("Режим сна", SLEEP[own], SLEEP[other], Fraction(own == other)))
        else:
            label, options = SCALES[key]
            similarity = Fraction(4 - abs(own - other), 4)
            result.append(Comparison(label, options[own - 1], options[other - 1], similarity))
    return tuple(result)


def directed_score(comparisons: tuple[Comparison, ...], weights: tuple[int, ...]) -> Fraction:
    return 100 * sum(item.similarity * weight for item, weight in zip(comparisons, weights, strict=True)) / sum(weights)


def compare(left: Questionnaire, right: Questionnaire) -> Recommendation | None:
    if (
        left.user_id == right.user_id or left.mode != right.mode
        or not ready(left) or not ready(right)
        or not accepts(left, right) or not accepts(right, left)
    ):
        return None

    conditions = ["Условия по курению и питомцам подходят обоим"]
    if left.mode == "rent":
        conditions.insert(0, "Диапазоны месячной доли пересекаются")
    elif left.dormitory_id == right.dormitory_id:
        conditions.insert(0, "Один вуз и общежитие")
    else:
        conditions.insert(0, "Один вуз, оба ищут по всему вузу")
    if not left.smokes and not right.smokes:
        conditions.append("Оба не курят")
    if not left.has_pet and not right.has_pet:
        conditions.append("У обоих нет питомцев")

    comparisons = compare_preferences(left, right)
    score = None
    if comparisons:
        weights = (1,) * len(comparisons)
        # Similarities are symmetric and both directions have the same initial weights.
        # Their mean therefore equals either normalized directional score.
        score = directed_score(comparisons, weights)
    return Recommendation(right.user_id, score, comparisons, tuple(conditions))


def rank(person: Questionnaire, candidates) -> list[Recommendation]:
    recommendations = [result for candidate in candidates if (result := compare(person, candidate)) is not None]
    return sorted(recommendations, key=lambda item: (item.score is None, -(item.score or 0), item.candidate_id))
