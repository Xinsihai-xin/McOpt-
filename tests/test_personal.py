"""Tests for personal recommender."""

from __future__ import annotations

from mcopt.models import UserNeed
from mcopt.personal import recommend_personal
from mcopt.scoring import filter_feasible, passes_hard_constraints, utility


def test_hard_constraints_budget(menu, budget_user):
    feasible = filter_feasible(menu, budget_user)
    assert feasible
    assert all(i.effective_price <= budget_user.budget for i in feasible)
    # Expensive burgers should be out
    names = {i.name for i in feasible}
    assert "巨无霸" not in names


def test_hard_constraints_disliked_tags(menu, light_eater):
    for item in menu:
        if "spicy" in item.tags:
            assert not passes_hard_constraints(item, light_eater)


def test_hard_constraints_max_calories(menu):
    need = UserNeed(
        budget=50.0,
        preferred_tags=(),
        disliked_tags=(),
        max_calories=300,
    )
    feasible = filter_feasible(menu, need)
    assert all(i.calories <= 300 for i in feasible)
    assert any(i.name == "玉米杯" for i in feasible)


def test_recommend_returns_three_modes(menu, light_eater):
    result = recommend_personal(menu, light_eater)
    assert result.best_overall is not None
    assert result.cheapest is not None
    assert result.nutrition_first is not None
    assert result.feasible
    assert result.best_overall.name in result.scores


def test_cheapest_is_lowest_effective_price(menu, light_eater):
    result = recommend_personal(menu, light_eater)
    assert result.cheapest is not None
    prices = [i.effective_price for i in result.feasible]
    assert result.cheapest.effective_price == min(prices)


def test_best_overall_has_max_utility(menu, spicy_fan):
    result = recommend_personal(menu, spicy_fan)
    assert result.best_overall is not None
    best_u = utility(result.best_overall, spicy_fan, menu)
    for item in result.feasible:
        assert utility(item, spicy_fan, menu) <= best_u + 1e-9


def test_empty_when_impossible(menu):
    need = UserNeed(
        budget=1.0,
        preferred_tags=("beef",),
        disliked_tags=("burger", "snack", "side", "dessert", "potato", "chicken", "fish", "sweet", "veggie"),
        max_calories=10,
    )
    result = recommend_personal(menu, need)
    assert result.best_overall is None
    assert result.cheapest is None
    assert result.nutrition_first is None
    assert result.feasible == ()
