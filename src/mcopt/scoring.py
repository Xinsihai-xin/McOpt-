"""Shared hard-constraint filters and multi-objective scoring."""

from __future__ import annotations

from typing import Iterable, Sequence

from .models import Item, UserNeed

# Default Utility weights: Preference, Nutrition, Value, Discount
DEFAULT_WEIGHTS: tuple[float, float, float, float] = (0.35, 0.25, 0.25, 0.15)


def passes_hard_constraints(item: Item, need: UserNeed) -> bool:
    """Return True iff the item satisfies budget / dislike / calorie hard rules."""
    if item.effective_price > need.budget:
        return False
    if need.disliked_set() & item.tag_set():
        return False
    if need.max_calories is not None and item.calories > need.max_calories:
        return False
    return True


def filter_feasible(items: Sequence[Item], need: UserNeed) -> list[Item]:
    """Keep only items that pass hard constraints for the given user."""
    return [item for item in items if passes_hard_constraints(item, need)]


def preference_score(item: Item, need: UserNeed) -> float:
    """
    Preference in [0, 1].
    Fraction of preferred tags present; spicy items get a small boost when
    'spicy' is preferred, and a small penalty when the user has no spicy preference.
    """
    preferred = need.preferred_set()
    tags = item.tag_set()
    if not preferred:
        base = 0.5
    else:
        hits = len(preferred & tags)
        base = hits / len(preferred)

    if "spicy" in preferred and item.spicy:
        base = min(1.0, base + 0.1)
    elif item.spicy and "spicy" not in preferred:
        base = max(0.0, base - 0.05)
    return base


def nutrition_score(item: Item, need: UserNeed, catalog: Sequence[Item]) -> float:
    """
    Nutrition in [0, 1], biased by nutrition_priority.
    Higher protein and lower calories are better when priority is high.
    """
    if not catalog:
        return 0.0

    max_protein = max(i.protein for i in catalog) or 1.0
    max_cal = max(i.calories for i in catalog) or 1.0
    protein_norm = item.protein / max_protein
    # Lower calories => higher score
    calorie_norm = 1.0 - (item.calories / max_cal)
    # Blend: nutrition_priority weights protein vs calorie lightness
    p = need.nutrition_priority
    return p * protein_norm + (1.0 - p) * calorie_norm


def value_score(item: Item, need: UserNeed, catalog: Sequence[Item]) -> float:
    """
    Value in [0, 1]: effective protein (and optionally satiety) per yuan.
    """
    if not catalog:
        return 0.0

    def raw_value(i: Item) -> float:
        price = max(i.effective_price, 1e-6)
        # Protein per yuan, lightly boosted by calories-per-yuan as "filling"
        return (i.protein / price) * (0.7 + 0.3 * need.value_priority) + (
            (i.calories / price) * 0.001 * need.value_priority
        )

    values = [raw_value(i) for i in catalog]
    vmax = max(values) or 1.0
    return raw_value(item) / vmax


def discount_score(item: Item) -> float:
    """Discount component already in [0, 1]."""
    return item.discount


def component_scores(
    item: Item, need: UserNeed, catalog: Sequence[Item]
) -> dict[str, float]:
    return {
        "preference": preference_score(item, need),
        "nutrition": nutrition_score(item, need, catalog),
        "value": value_score(item, need, catalog),
        "discount": discount_score(item),
    }


def utility(
    item: Item,
    need: UserNeed,
    catalog: Sequence[Item],
    weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS,
) -> float:
    """
    Utility = w1*Preference + w2*Nutrition + w3*Value + w4*Discount
    Weights are normalized to sum to 1.
    """
    w1, w2, w3, w4 = weights
    total = w1 + w2 + w3 + w4
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    w1, w2, w3, w4 = w1 / total, w2 / total, w3 / total, w4 / total
    c = component_scores(item, need, catalog)
    return (
        w1 * c["preference"]
        + w2 * c["nutrition"]
        + w3 * c["value"]
        + w4 * c["discount"]
    )


def satisfaction(item: Item, need: UserNeed, catalog: Sequence[Item]) -> float:
    """Alias used by group scoring: personal utility as satisfaction in [0, ~1]."""
    return utility(item, need, catalog)


def normalize_weights(scores: Iterable[float]) -> list[float]:
    """Convert non-negative scores into a probability distribution."""
    vals = [max(0.0, float(s)) for s in scores]
    total = sum(vals)
    if total <= 0:
        n = len(vals)
        return [1.0 / n] * n if n else []
    return [v / total for v in vals]
