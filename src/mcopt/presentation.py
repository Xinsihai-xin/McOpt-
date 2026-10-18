"""UI orchestration; core scoring and recommendation algorithms stay unchanged."""
from dataclasses import dataclass, replace
import random

from .scoring import component_scores, DEFAULT_WEIGHTS, filter_feasible, satisfaction
from .group import group_score
from .blind_box import recommend_blind_box, BlindBoxResult


def explanation(item, need, catalog, weights=DEFAULT_WEIGHTS):
    components = component_scores(item, need, catalog)
    total = sum(weights)
    return [dict(component=name, score=value, weight=w / total,
                 contribution=value * w / total)
            for (name, value), w in zip(components.items(), weights)]


@dataclass(frozen=True)
class Compromise:
    item: object
    members: tuple
    changes: tuple
    member_scores: tuple
    group_score: float
    cost: float
    direction: str


def compromises(catalog, members, lambda_=0.6):
    """Minimum normalized relaxation per direction among current catalog items.

    Cost = sum(delta_budget/max(old_budget,1) + delta_kcal/max(old_cap,1)).
    Disliked tags are never relaxed. Return best budget-only, calories-only and
    combined candidate when each exists. These are suggestions, not mutations.
    """
    best = {}
    for item in catalog:
        if any(m.disliked_set() & item.tag_set() for m in members):
            continue
        updated, changes, cost, kinds = [], [], 0.0, set()
        for index, m in enumerate(members):
            budget = max(m.budget, item.effective_price)
            cap = None if m.max_calories is None else max(m.max_calories, item.calories)
            if budget > m.budget:
                changes.append((index + 1, '预算（¥）', m.budget, budget))
                cost += (budget - m.budget) / max(m.budget, 1)
                kinds.add('预算')
            if cap is not None and cap > m.max_calories:
                changes.append((index + 1, '热量（kcal）', m.max_calories, cap))
                cost += (cap - m.max_calories) / max(m.max_calories, 1)
                kinds.add('热量')
            updated.append(replace(m, budget=budget, max_calories=cap))
        if not changes:
            continue
        direction = ' + '.join(sorted(kinds))
        scores = tuple(satisfaction(item, m, catalog) for m in updated)
        suggestion = Compromise(item, tuple(updated), tuple(changes), scores,
                                group_score(scores, lambda_), cost, direction)
        key = (cost, len(changes), -suggestion.group_score, item.effective_price)
        if direction not in best or key < best[direction][0]:
            best[direction] = (key, suggestion)
    return [s for _, s in sorted(best.values(), key=lambda pair: pair[0])]


def draw_with_history(items, need, mode, history, avoid_recent=True, rng=None):
    """Reuse full-catalog normalization/history, condition existing probabilities.

    If all feasible items were seen in the last three draws, allow repeats and
    return an explicit fallback flag; never relax budget/calorie/dislike rules.
    """
    rng = rng or random.Random()
    base = recommend_blind_box(items, need, mode=mode, history=history, rng=rng)
    recent = set(history[-3:]) if avoid_recent else set()
    candidates = tuple(i for i in base.feasible if i.name not in recent)
    fallback = bool(base.feasible and not candidates)
    if not candidates:
        candidates = base.feasible
    if not candidates:
        return base, False
    from .blind_box import blind_box_score
    from .scoring import normalize_weights
    probs = normalize_weights(base.probabilities[i.name] for i in candidates)
    chosen = rng.choices(candidates, weights=probs, k=1)[0]
    by_name = {i.name: i for i in items}
    history_items = [by_name[n] for n in history if n in by_name]
    score = blind_box_score(chosen, need, items, history, history_items, base.mode)
    return BlindBoxResult(chosen, base.mode, score,
                          dict(zip((i.name for i in candidates), probs)), candidates), fallback
