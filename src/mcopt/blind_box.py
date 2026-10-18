"""Blind-box recommender: hard constraints + Utility / Novelty / Diversity."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .models import Item, UserNeed
from .scoring import filter_feasible, normalize_weights, utility


class BlindBoxMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    ADVENTUROUS = "adventurous"


# BlindBoxScore = α*Utility + β*Novelty + γ*Diversity
# More adventurous => higher Novelty / Diversity weights.
_MODE_WEIGHTS: dict[BlindBoxMode, tuple[float, float, float]] = {
    BlindBoxMode.CONSERVATIVE: (0.70, 0.20, 0.10),
    BlindBoxMode.BALANCED: (0.50, 0.30, 0.20),
    BlindBoxMode.ADVENTUROUS: (0.30, 0.40, 0.30),
}


@dataclass(frozen=True)
class BlindBoxResult:
    item: Item | None
    mode: BlindBoxMode
    score: float
    probabilities: dict[str, float]
    feasible: tuple[Item, ...]


def novelty_score(
    item: Item,
    history: Sequence[str],
    catalog: Sequence[Item],
) -> float:
    """
    Novelty in [0, 1]: items never (or rarely) seen in history score higher.
    """
    if not history:
        return 1.0
    name = item.name
    count = sum(1 for h in history if h == name)
    # Unseen => 1.0; more repeats => closer to 0
    return 1.0 / (1.0 + count)


def diversity_score(
    item: Item,
    history_items: Sequence[Item],
    catalog: Sequence[Item],
) -> float:
    """
    Diversity in [0, 1]: reward category / tag difference from recent history.
    """
    if not history_items:
        return 1.0

    categories = {h.category for h in history_items}
    hist_tags: set[str] = set()
    for h in history_items:
        hist_tags |= h.tag_set()

    cat_bonus = 1.0 if item.category not in categories else 0.0
    if not item.tag_set():
        tag_bonus = 0.5
    else:
        new_tags = item.tag_set() - hist_tags
        tag_bonus = len(new_tags) / len(item.tag_set())
    return 0.6 * cat_bonus + 0.4 * tag_bonus


def blind_box_score(
    item: Item,
    need: UserNeed,
    catalog: Sequence[Item],
    history: Sequence[str],
    history_items: Sequence[Item],
    mode: BlindBoxMode,
) -> float:
    """BlindBoxScore = α*Utility + β*Novelty + γ*Diversity."""
    alpha, beta, gamma = _MODE_WEIGHTS[mode]
    u = utility(item, need, catalog)
    n = novelty_score(item, history, catalog)
    d = diversity_score(item, history_items, catalog)
    return alpha * u + beta * n + gamma * d


def recommend_blind_box(
    items: Sequence[Item],
    need: UserNeed,
    mode: BlindBoxMode | str = BlindBoxMode.BALANCED,
    history: Sequence[str] | None = None,
    rng: random.Random | None = None,
) -> BlindBoxResult:
    """
    Hard-constraint filter, then weighted sample by BlindBoxScore.

    Probability mass is proportional to BlindBoxScore (not uniform random.choice).
    """
    if isinstance(mode, str):
        mode = BlindBoxMode(mode)
    history = list(history or ())
    rng = rng or random.Random()

    name_to_item = {i.name: i for i in items}
    history_items = [name_to_item[h] for h in history if h in name_to_item]

    feasible = filter_feasible(items, need)
    if not feasible:
        return BlindBoxResult(
            item=None,
            mode=mode,
            score=0.0,
            probabilities={},
            feasible=(),
        )

    scores = [
        blind_box_score(item, need, items, history, history_items, mode)
        for item in feasible
    ]
    probs = normalize_weights(scores)
    prob_map = {item.name: p for item, p in zip(feasible, probs)}

    # Weighted random sample driven by BlindBoxScore-derived probabilities.
    chosen = rng.choices(feasible, weights=probs, k=1)[0]
    chosen_score = blind_box_score(
        chosen, need, items, history, history_items, mode
    )

    return BlindBoxResult(
        item=chosen,
        mode=mode,
        score=chosen_score,
        probabilities=prob_map,
        feasible=tuple(feasible),
    )
