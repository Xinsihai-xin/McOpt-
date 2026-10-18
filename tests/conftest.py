"""Shared fixtures: 10 virtual McDonald's menu items."""

from __future__ import annotations

import pytest

from mcopt.models import Item, UserNeed


@pytest.fixture
def menu() -> list[Item]:
    return [
        Item(
            name="巨无霸",
            price=26.0,
            calories=540,
            protein=25,
            category="burger",
            spicy=False,
            tags=("beef", "classic", "burger"),
            discount=0.0,
        ),
        Item(
            name="双层吉士汉堡",
            price=18.0,
            calories=450,
            protein=22,
            category="burger",
            spicy=False,
            tags=("beef", "cheese", "burger"),
            discount=0.1,
        ),
        Item(
            name="麦辣鸡腿堡",
            price=22.0,
            calories=490,
            protein=24,
            category="burger",
            spicy=True,
            tags=("chicken", "spicy", "burger"),
            discount=0.0,
        ),
        Item(
            name="板烧鸡腿堡",
            price=23.0,
            calories=430,
            protein=26,
            category="burger",
            spicy=False,
            tags=("chicken", "grilled", "burger"),
            discount=0.05,
        ),
        Item(
            name="麦香鱼",
            price=20.0,
            calories=370,
            protein=16,
            category="burger",
            spicy=False,
            tags=("fish", "light", "burger"),
            discount=0.0,
        ),
        Item(
            name="麦乐鸡(5块)",
            price=13.0,
            calories=250,
            protein=14,
            category="snack",
            spicy=False,
            tags=("chicken", "snack", "share"),
            discount=0.15,
        ),
        Item(
            name="薯条(中)",
            price=12.0,
            calories=340,
            protein=4,
            category="side",
            spicy=False,
            tags=("potato", "side", "share"),
            discount=0.0,
        ),
        Item(
            name="玉米杯",
            price=11.0,
            calories=140,
            protein=5,
            category="side",
            spicy=False,
            tags=("veggie", "light", "side"),
            discount=0.0,
        ),
        Item(
            name="麦辣鸡翅(2块)",
            price=14.0,
            calories=280,
            protein=18,
            category="snack",
            spicy=True,
            tags=("chicken", "spicy", "snack"),
            discount=0.1,
        ),
        Item(
            name="草莓新地",
            price=10.0,
            calories=270,
            protein=5,
            category="dessert",
            spicy=False,
            tags=("sweet", "dessert", "cold"),
            discount=0.2,
        ),
    ]


@pytest.fixture
def light_eater() -> UserNeed:
    return UserNeed(
        budget=25.0,
        preferred_tags=("light", "chicken", "grilled"),
        disliked_tags=("spicy",),
        max_calories=500,
        nutrition_priority=0.8,
        value_priority=0.4,
    )


@pytest.fixture
def spicy_fan() -> UserNeed:
    return UserNeed(
        budget=30.0,
        preferred_tags=("spicy", "chicken"),
        disliked_tags=("fish",),
        max_calories=600,
        nutrition_priority=0.4,
        value_priority=0.6,
    )


@pytest.fixture
def budget_user() -> UserNeed:
    return UserNeed(
        budget=15.0,
        preferred_tags=("share", "snack"),
        disliked_tags=("dessert",),
        max_calories=400,
        nutrition_priority=0.3,
        value_priority=0.9,
    )
