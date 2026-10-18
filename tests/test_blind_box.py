"""Tests for blind-box recommender."""

from __future__ import annotations

import random

import pytest

from mcopt.blind_box import (
    BlindBoxMode,
    blind_box_score,
    novelty_score,
    recommend_blind_box,
)
from mcopt.models import UserNeed
from mcopt.scoring import passes_hard_constraints


def test_modes_accepted(menu, spicy_fan):
    rng = random.Random(0)
    for mode in BlindBoxMode:
        result = recommend_blind_box(menu, spicy_fan, mode=mode, rng=rng)
        assert result.item is not None
        assert result.mode == mode
        assert abs(sum(result.probabilities.values()) - 1.0) < 1e-9


def test_not_uniform_random_choice(menu, spicy_fan):
    """Probabilities must come from BlindBoxScore, not equal weights."""
    rng = random.Random(1)
    result = recommend_blind_box(
        menu, spicy_fan, mode=BlindBoxMode.BALANCED, history=[], rng=rng
    )
    probs = list(result.probabilities.values())
    assert len(probs) >= 2
    # With non-trivial score differences, not all probs equal
    assert max(probs) - min(probs) > 1e-6 or len(set(round(p, 6) for p in probs)) > 1


def test_hard_constraints_respected(menu, light_eater):
    rng = random.Random(42)
    for _ in range(30):
        result = recommend_blind_box(
            menu, light_eater, mode="adventurous", history=["巨无霸"], rng=rng
        )
        assert result.item is not None
        assert passes_hard_constraints(result.item, light_eater)
        assert "spicy" not in result.item.tags


def test_novelty_penalizes_history(menu):
    item = menu[0]
    unseen = novelty_score(item, [], menu)
    seen_once = novelty_score(item, [item.name], menu)
    seen_twice = novelty_score(item, [item.name, item.name], menu)
    assert unseen > seen_once > seen_twice


def test_adventurous_boosts_novelty_weight(menu, spicy_fan):
    history = ["巨无霸", "巨无霸", "双层吉士汉堡"]
    history_items = [i for i in menu if i.name in history]
    # Pick a rarely seen spicy item vs a historically repeated one if both feasible
    feasible = [i for i in menu if passes_hard_constraints(i, spicy_fan)]
    assert len(feasible) >= 2

    cons = {
        i.name: blind_box_score(
            i, spicy_fan, menu, history, history_items, BlindBoxMode.CONSERVATIVE
        )
        for i in feasible
    }
    adv = {
        i.name: blind_box_score(
            i, spicy_fan, menu, history, history_items, BlindBoxMode.ADVENTUROUS
        )
        for i in feasible
    }
    # Relative score of a novel item vs a repeated one should rise under adventurous
    novel = next(i for i in feasible if i.name not in history)
    repeated = next(i for i in feasible if i.name in history)
    cons_ratio = cons[novel.name] / max(cons[repeated.name], 1e-9)
    adv_ratio = adv[novel.name] / max(adv[repeated.name], 1e-9)
    assert adv_ratio >= cons_ratio - 1e-9


def test_probabilities_sum_to_one(menu, budget_user):
    result = recommend_blind_box(
        menu, budget_user, mode=BlindBoxMode.CONSERVATIVE, rng=random.Random(7)
    )
    assert result.item is not None
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-9
    assert result.item.name in result.probabilities


def test_empty_feasible(menu):
    need = UserNeed(budget=0.5, disliked_tags=("burger", "snack", "side", "dessert", "potato", "chicken", "fish", "sweet", "veggie", "beef", "share"))
    result = recommend_blind_box(menu, need, mode="balanced", rng=random.Random(0))
    assert result.item is None
    assert result.probabilities == {}


def test_invalid_mode_raises(menu, spicy_fan):
    with pytest.raises(ValueError):
        recommend_blind_box(menu, spicy_fan, mode="chaos", rng=random.Random(0))
