"""Personal recommender: hard constraints + multi-objective Utility ranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import Item, UserNeed
from .scoring import (
    DEFAULT_WEIGHTS,
    filter_feasible,
    nutrition_score,
    utility,
)


@dataclass(frozen=True)
class PersonalRecommendation:
    """Three complementary picks from the feasible set."""

    best_overall: Item | None
    cheapest: Item | None
    nutrition_first: Item | None
    feasible: tuple[Item, ...]
    scores: dict[str, float]  # item name -> utility


def recommend_personal(
    items: Sequence[Item],
    need: UserNeed,
    weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS,
) -> PersonalRecommendation:
    """
    1. Filter by hard constraints (budget / disliked tags / max calories).
    2. Score feasible items with Utility.
    3. Return overall best, cheapest, and nutrition-first picks.
    """
    feasible = filter_feasible(items, need)
    if not feasible:
        return PersonalRecommendation(
            best_overall=None,
            cheapest=None,
            nutrition_first=None,
            feasible=(),
            scores={},
        )

    scores = {item.name: utility(item, need, items, weights) for item in feasible}

    best_overall = max(feasible, key=lambda i: scores[i.name])
    cheapest = min(feasible, key=lambda i: (i.effective_price, -scores[i.name]))
    nutrition_first = max(
        feasible,
        key=lambda i: (
            nutrition_score(i, need, items),
            scores[i.name],
        ),
    )

    return PersonalRecommendation(
        best_overall=best_overall,
        cheapest=cheapest,
        nutrition_first=nutrition_first,
        feasible=tuple(feasible),
        scores=scores,
    )
