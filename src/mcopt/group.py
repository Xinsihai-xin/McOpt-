"""Group recommendations balancing average and minimum satisfaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import Item, UserNeed
from .scoring import passes_hard_constraints, satisfaction


@dataclass(frozen=True)
class GroupRecommendation:
    item: Item | None
    member_scores: tuple[float, ...]
    group_score: float

    @property
    def feasible_for_all(self) -> bool:
        """Whether a recommendation satisfying every member was found."""
        return self.item is not None


def group_score(scores: Sequence[float], lambda_: float = 0.6) -> float:
    """Blend mean satisfaction with the least satisfied member's score."""
    if not 0.0 <= lambda_ <= 1.0:
        raise ValueError("lambda_ must be in [0, 1]")
    if not scores:
        return 0.0
    return lambda_ * (sum(scores) / len(scores)) + (1.0 - lambda_) * min(scores)


def recommend_group(
    catalog: Sequence[Item],
    members: Sequence[UserNeed],
    lambda_: float = 0.6,
) -> GroupRecommendation:
    """Choose the highest-scoring item feasible for all two to six members."""
    if not 2 <= len(members) <= 6:
        raise ValueError("group size must be between 2 and 6")
    if not 0.0 <= lambda_ <= 1.0:
        raise ValueError("lambda_ must be in [0, 1]")

    best = GroupRecommendation(item=None, member_scores=(), group_score=0.0)
    best_key = None
    for item in catalog:
        if not all(passes_hard_constraints(item, member) for member in members):
            continue
        scores = tuple(satisfaction(item, member, catalog) for member in members)
        score = group_score(scores, lambda_=lambda_)
        # Resolve ties by minimum satisfaction, mean satisfaction, then price.
        # Exact ties retain the first item in catalog order.
        key = (score, min(scores), sum(scores) / len(scores), -item.effective_price)
        if best_key is None or key > best_key:
            best_key = key
            best = GroupRecommendation(item=item, member_scores=scores, group_score=score)
    return best
