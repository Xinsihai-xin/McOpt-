"""McOpt-X local core algorithms (Phase 1 MVP)."""

from .blind_box import BlindBoxMode, recommend_blind_box
from .models import Item, UserNeed
from .personal import PersonalRecommendation, recommend_personal

__all__ = [
    "Item",
    "UserNeed",
    "PersonalRecommendation",
    "recommend_personal",
    "recommend_group",
    "BlindBoxMode",
    "recommend_blind_box",
]

__version__ = "0.1.0"


def __getattr__(name):
    # Keep Personal usable when the optional Group source is unavailable.
    if name == "recommend_group":
        from .group import recommend_group
        return recommend_group
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
