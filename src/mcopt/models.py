"""Core data structures for menu items and user needs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class Item:
    """A McDonald's menu item used by local recommenders."""

    name: str
    price: float
    calories: float
    protein: float
    category: str
    spicy: bool = False
    tags: tuple[str, ...] = ()
    discount: float = 0.0  # fraction off list price, e.g. 0.2 = 20% off

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError("price must be non-negative")
        if self.calories < 0:
            raise ValueError("calories must be non-negative")
        if self.protein < 0:
            raise ValueError("protein must be non-negative")
        if not 0.0 <= self.discount <= 1.0:
            raise ValueError("discount must be in [0, 1]")
        # Normalize tags to a tuple for hashability / immutability.
        object.__setattr__(self, "tags", tuple(self.tags))

    @property
    def effective_price(self) -> float:
        """Price after applying discount."""
        return self.price * (1.0 - self.discount)

    def tag_set(self) -> set[str]:
        return set(self.tags)


@dataclass(frozen=True)
class UserNeed:
    """User constraints and soft priorities for ranking."""

    budget: float
    preferred_tags: Sequence[str] = field(default_factory=tuple)
    disliked_tags: Sequence[str] = field(default_factory=tuple)
    max_calories: float | None = None
    nutrition_priority: float = 0.5  # higher => prefer protein / lower calories
    value_priority: float = 0.5  # higher => prefer more protein / calorie per yuan

    def __post_init__(self) -> None:
        if self.budget < 0:
            raise ValueError("budget must be non-negative")
        if self.max_calories is not None and self.max_calories < 0:
            raise ValueError("max_calories must be non-negative")
        if not 0.0 <= self.nutrition_priority <= 1.0:
            raise ValueError("nutrition_priority must be in [0, 1]")
        if not 0.0 <= self.value_priority <= 1.0:
            raise ValueError("value_priority must be in [0, 1]")
        object.__setattr__(self, "preferred_tags", tuple(self.preferred_tags))
        object.__setattr__(self, "disliked_tags", tuple(self.disliked_tags))

    def preferred_set(self) -> set[str]:
        return set(self.preferred_tags)

    def disliked_set(self) -> set[str]:
        return set(self.disliked_tags)
