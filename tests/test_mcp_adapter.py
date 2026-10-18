"""Minimal real-data test for the MCP adapter (no algorithm changes)."""

from __future__ import annotations

from pathlib import Path

from mcopt.mcp_adapter import items_from_mcp, load_json
from mcopt.models import Item

FIXTURES = Path(__file__).parent / "fixtures"


def test_adapter_maps_real_mcp_menu_and_nutrition():
    meals = load_json(str(FIXTURES / "mcp_meals_min.json"))
    nutrition = load_json(str(FIXTURES / "mcp_nutrition_min.json"))

    items = items_from_mcp(meals, nutrition)
    by_name = {item.name: item for item in items}

    assert isinstance(items[0], Item)
    assert set(by_name) >= {
        "巨无霸",
        "双层吉士汉堡",
        "板烧鸡腿堡",
        "麦辣鸡腿汉堡",
        "薯条",
        "玉米杯",
        "马苏里拉拉丝芝士条",
        "巨无霸三件套",
    }

    big_mac = by_name["巨无霸"]
    assert big_mac.category == "巨无霸/牛鱼肉堡"
    assert big_mac.price == 26.5
    assert big_mac.calories == 513
    assert big_mac.protein == 27
    assert big_mac.discount == 0.0

    fries = by_name["薯条"]
    assert fries.calories == 289
    assert fries.protein == 4

    spicy_burger = by_name["麦辣鸡腿汉堡"]
    assert spicy_burger.calories == 485
    assert spicy_burger.spicy is True

    cheese_sticks = by_name["马苏里拉拉丝芝士条"]
    assert cheese_sticks.price == 16.0
    assert abs(cheese_sticks.discount - (1.0 - 11.0 / 16.0)) < 1e-9
    assert cheese_sticks.calories == 0.0  # no nutrition row in catalog

    combo = by_name["巨无霸三件套"]
    assert combo.calories == 0.0
    assert combo.protein == 0.0
    assert abs(combo.discount - (1.0 - 37.5 / 51.0)) < 1e-9
