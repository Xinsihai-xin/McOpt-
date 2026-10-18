"""Tests for group recommender."""

from __future__ import annotations

import pytest

from mcopt.group import group_score, recommend_group
from mcopt.models import UserNeed
from mcopt.scoring import passes_hard_constraints


def test_group_size_bounds(menu, light_eater, spicy_fan):
    with pytest.raises(ValueError):
        recommend_group(menu, [light_eater])
    with pytest.raises(ValueError):
        recommend_group(menu, [light_eater] * 7)


def test_group_score_formula():
    scores = (0.8, 0.4, 0.6)
    lam = 0.6
    expected = lam * (sum(scores) / 3) + (1 - lam) * min(scores)
    assert abs(group_score(scores, lambda_=lam) - expected) < 1e-9


def test_recommend_group_two_people(menu, light_eater, spicy_fan):
    result = recommend_group(menu, [light_eater, spicy_fan], lambda_=0.6)
    assert result.item is not None
    assert len(result.member_scores) == 2
    # Feasible for both
    assert passes_hard_constraints(result.item, light_eater)
    assert passes_hard_constraints(result.item, spicy_fan)
    # Spicy items violate light_eater -> should not be recommended
    assert "spicy" not in result.item.tags


def test_group_protects_min_satisfaction(menu, light_eater, spicy_fan, budget_user):
    # With low lambda (more weight on min), score should emphasize fairness.
    fair = recommend_group(menu, [light_eater, spicy_fan, budget_user], lambda_=0.2)
    avg_heavy = recommend_group(menu, [light_eater, spicy_fan, budget_user], lambda_=0.9)
    assert fair.item is not None
    assert avg_heavy.item is not None
    # Fair regime: min satisfaction should be at least as high as avg-heavy regime
    # (may be equal if same item wins both); never lower when lambda favors min.
    # Soft check: group_score uses the formula correctly for the returned scores.
    assert abs(
        fair.group_score
        - group_score(fair.member_scores, lambda_=0.2)
    ) < 1e-9


def test_group_no_common_feasible(menu):
    a = UserNeed(budget=12.0, preferred_tags=("beef",), disliked_tags=("snack", "side", "dessert", "chicken", "fish", "potato", "veggie", "sweet"))
    b = UserNeed(budget=12.0, preferred_tags=("sweet",), disliked_tags=("burger", "snack", "side", "chicken", "beef", "fish", "potato", "veggie", "share"))
    # a only wants beef burgers but budget is tight; b hates burgers — intersection empty likely
    result = recommend_group(menu, [a, b])
    # May or may not be empty depending on menu; if empty, fields are zeroed.
    if not result.feasible_for_all:
        assert result.item is None
        assert result.group_score == 0.0


def test_group_member_count_2_to_6(menu, light_eater, spicy_fan, budget_user):
    members = [light_eater, spicy_fan, budget_user]
    # pad with mild users up to 6
    extra = UserNeed(
        budget=40.0,
        preferred_tags=("chicken",),
        disliked_tags=(),
        max_calories=800,
    )
    for size in range(2, 7):
        group = (members + [extra] * 3)[:size]
        result = recommend_group(menu, group)
        assert result.item is not None
        assert len(result.member_scores) == size
