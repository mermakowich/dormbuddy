from dataclasses import replace
from fractions import Fraction

import pytest

from dormbuddy.matching import Questionnaire, compare, rank


def renter(user_id, **changes):
    return replace(Questionnaire(
        user_id=user_id, display_name=f"Студент {user_id}", budget_min=20_000, budget_max=30_000,
        smokes=False, allows_smoking=False, has_pet=False, allows_pets=False,
    ), **changes)


@pytest.mark.parametrize("changes", [
    {"budget_min": 30_001, "budget_max": 40_000},
    {"budget_max": None},
    {"smokes": True},
    {"has_pet": True},
    {"allows_pets": None},
])
def test_obligatory_constraints_are_bidirectional(changes):
    a, b = renter(1), renter(2, **changes)
    assert compare(a, b) is None
    assert compare(b, a) is None


def test_touching_budgets_and_different_universities():
    a = renter(1, university_id=1)
    b = renter(2, budget_min=30_000, budget_max=40_000, university_id=2)
    assert "Диапазоны месячной доли пересекаются" in compare(a, b).conditions
    assert compare(a, a) is None


def test_dorm_does_not_use_budget_and_scope_is_bidirectional():
    a = renter(1, mode="dorm", university_id=1, dormitory_id=1, budget_min=None, budget_max=None)
    b = replace(a, user_id=2, dormitory_id=2, dorm_scope="university")
    other_university = replace(b, university_id=2)
    assert compare(a, replace(b, dormitory_id=1))
    assert compare(a, b) is None and compare(b, a) is None
    assert compare(replace(a, dorm_scope="university"), b)
    assert compare(replace(a, dorm_scope="university"), other_university) is None


def test_exact_score_is_symmetric_and_uses_only_compared_preferences():
    a = renter(1, preferences={"sleep": "early", "cleaning": 1, "guests": 5})
    b = renter(2, preferences={"sleep": "early", "cleaning": 3})
    result = compare(a, b)
    assert result.score == compare(b, a).score == 75
    assert [(item.label, item.similarity) for item in result.comparisons] == [
        ("Режим сна", 1), ("Уборка", Fraction(1, 2)),
    ]
    assert compare(replace(a, preferences=b.preferences), b).score == 100


def test_ranking_distinguishes_zero_from_missing_and_breaks_ties_by_id():
    a = renter(10, preferences={"sleep": "early", "cleaning": 1})
    candidates = [
        renter(1), renter(4, preferences={"sleep": "late"}), renter(3, preferences={"sleep": "late"}),
        renter(2, preferences={"cleaning": 4}),
    ]
    assert [(item.candidate_id, item.display_score) for item in rank(a, candidates)] == [
        (2, 25), (3, 0), (4, 0), (1, None),
    ]
