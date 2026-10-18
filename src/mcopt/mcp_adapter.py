"""McDonald's MCP → Phase 1 Item adapter.

Does not change Personal / Group / Blind Box scoring. It only normalizes
query-meals + list-nutrition-foods payloads into `mcopt.models.Item`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from .models import Item

# Explicit aliases when menu names and nutrition names diverge.
_NAME_ALIASES: dict[str, str] = {
    "麦辣鸡腿堡": "麦辣鸡腿汉堡",
    "阳光橙麦炫酷": "麦旋酷阳光橙",
    "可乐": "可乐中杯",
    "雪碧": "雪碧中杯",
    "薯条": "中薯条",
    "麦乐鸡": "麦乐鸡5块",
    "玉米杯": "大杯玉米杯",
    "麦辣鸡翅": "麦辣鸡翅2块",
    "100苹果汁盒装": "100苹果汁",
    "那么大鸡排椒盐风味": "那么大鸡排",
    "纯牛奶盒装": "纯牛奶盒装",
    "牛气满满套餐": "牛气满满",
    "苹板支撑pro套餐": "苹板支撑pro",
    "苹板支撑pro": "苹板支撑pro",
}

_COMBO_MARKERS = (
    "三件套",
    "四件套",
    "双人",
    "随心选",
    "随心配",
    "拼盘",
    "分享餐",
    "乐园餐",
    "亲子",
    "八件套",
    "十翅",
)

_SIZE_TOKENS = (
    "中杯",
    "大杯",
    "小杯",
    "迷你",
    "盒装",
    "中份",
    "大份",
    "小份",
)

_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
_BLOCK_RE = re.compile(r"[（(].*?[）)]")


def normalize_name(name: str) -> str:
    """Collapse menu / nutrition titles into a comparable token."""
    text = unicodedata.normalize("NFKC", name or "")
    text = text.replace("™", "").replace("®", "").replace("“", "").replace("”", "")
    text = text.replace("-", "").replace("—", "")
    text = _BLOCK_RE.sub("", text)
    text = _PUNCT_RE.sub("", text)
    return text.casefold().strip()


def _canonical_name(name: str) -> str:
    key = normalize_name(name)
    return _NAME_ALIASES.get(key, key)


def _looks_like_combo(name: str) -> bool:
    return any(marker in name for marker in _COMBO_MARKERS)


def _strip_size(token: str) -> str:
    out = token
    for size in _SIZE_TOKENS:
        size_n = normalize_name(size)
        if out.endswith(size_n):
            out = out[: -len(size_n)]
        out = out.replace(size_n, "")
    return out


def _parse_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_nutrition_foods(payload: Any) -> list[dict[str, Any]]:
    """Parse list-nutrition-foods. `data` may be a CSV-like string or a list."""
    root = payload
    if isinstance(payload, Mapping) and "data" in payload:
        root = payload["data"]

    if isinstance(root, list):
        rows: list[dict[str, Any]] = []
        for row in root:
            if not isinstance(row, Mapping):
                continue
            name = str(row.get("productName") or row.get("name") or "")
            if not name:
                continue
            rows.append(
                {
                    "name": name,
                    "calories": _parse_float(
                        row.get("energyKcal") or row.get("calories")
                    ),
                    "protein": _parse_float(row.get("protein")),
                }
            )
        return rows

    if not isinstance(root, str):
        return []

    text = root.strip()
    header_match = re.search(r"\{([^}]+)\}:", text)
    if not header_match:
        return []
    columns = [c.strip() for c in header_match.group(1).split(",")]
    body = text[header_match.end() :]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(columns):
            continue
        record = dict(zip(columns, parts))
        name = record.get("productName") or ""
        if not name:
            continue
        kcal = record.get("energyKcal")
        protein = record.get("protein")
        if kcal in {None, "", "null"}:
            continue
        rows.append(
            {
                "name": name,
                "calories": _parse_float(kcal),
                "protein": _parse_float(protein),
            }
        )
    return rows


def _match_score(menu_name: str, nutrition_name: str) -> float:
    """Higher is better. 0 means no acceptable match."""
    if _looks_like_combo(menu_name) and not _looks_like_combo(nutrition_name):
        # Named 500kcal meals like 牛气满满套餐 ↔ 牛气满满 are allowed below.
        menu_core = normalize_name(menu_name.replace("套餐", ""))
        nutri_core = normalize_name(nutrition_name)
        if menu_core != nutri_core and menu_core != _canonical_name(nutrition_name):
            if not (
                menu_core.endswith(nutri_core)
                and len(nutri_core) >= 4
                and not _looks_like_combo(menu_name.replace("套餐", ""))
            ):
                # 巨无霸三件套 must not inherit 巨无霸 nutrition.
                if any(m in menu_name for m in ("三件套", "四件套", "双人", "随心")):
                    return 0.0

    a = _canonical_name(menu_name)
    b = _canonical_name(nutrition_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    a_size = _strip_size(a)
    b_size = _strip_size(b)
    if a_size and a_size == b_size:
        return 0.92

    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 3:
            return 0.75 * (len(shorter) / len(longer))
    return 0.0


def match_nutrition(
    menu_name: str, nutrition_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    """Pick the best nutrition row for a menu title, or None."""
    best: dict[str, Any] | None = None
    best_score = 0.0
    for row in nutrition_rows:
        score = _match_score(menu_name, str(row.get("name", "")))
        if score > best_score:
            best_score = score
            best = dict(row)
    if best_score < 0.7:
        return None
    return best


def _iter_menu_entries(
    meals_payload: Mapping[str, Any],
) -> Iterable[dict[str, Any]]:
    data = meals_payload.get("data", meals_payload)
    if not isinstance(data, Mapping):
        return
    meals_map = data.get("meals") or {}
    categories = data.get("categories") or []
    seen: set[str] = set()
    for category in categories:
        if not isinstance(category, Mapping):
            continue
        cat_name = str(category.get("name") or "").replace("\n", "/")
        for ref in category.get("meals") or []:
            if not isinstance(ref, Mapping):
                continue
            code = str(ref.get("code") or "")
            if not code or code in seen:
                continue
            detail = meals_map.get(code)
            if not isinstance(detail, Mapping):
                continue
            seen.add(code)
            yield {
                "code": code,
                "category": cat_name,
                "tags": tuple(ref.get("tags") or ()),
                "detail": detail,
            }


def _discount_from_prices(current: float, original: float) -> float:
    if original <= 0 or current < 0 or current > original:
        return 0.0
    if original == current:
        return 0.0
    return max(0.0, min(1.0, 1.0 - current / original))


def meal_to_item(
    entry: Mapping[str, Any],
    nutrition_rows: Sequence[Mapping[str, Any]],
) -> Item | None:
    detail = entry.get("detail") or {}
    if not isinstance(detail, Mapping):
        return None
    name = str(detail.get("name") or "").strip()
    if not name:
        return None

    original = _parse_float(detail.get("originalPrice"))
    current = _parse_float(detail.get("currentPrice"), default=original)
    price = original if original > 0 else current
    discount = _discount_from_prices(current, price)

    nutri = match_nutrition(name, nutrition_rows)
    calories = float(nutri["calories"]) if nutri else 0.0
    protein = float(nutri["protein"]) if nutri else 0.0

    tags = tuple(str(t) for t in (entry.get("tags") or ()))
    spicy = any("辣" in t for t in tags) or ("辣" in name)

    return Item(
        name=name,
        price=price,
        calories=calories,
        protein=protein,
        category=str(entry.get("category") or "unknown"),
        spicy=spicy,
        tags=tags,
        discount=discount,
    )


def items_from_mcp(
    meals_payload: Mapping[str, Any],
    nutrition_payload: Any,
    promotions_payload: Any | None = None,
) -> list[Item]:
    """Convert MCP meal + nutrition payloads into Phase 1 Item objects.

    `promotions_payload` is accepted for forward compatibility. v1 discount
    comes from query-meals originalPrice vs currentPrice when present.
    """
    _ = promotions_payload  # unused in v1; price gap already encodes offers
    nutrition_rows = parse_nutrition_foods(nutrition_payload)
    items: list[Item] = []
    for entry in _iter_menu_entries(meals_payload):
        item = meal_to_item(entry, nutrition_rows)
        if item is not None:
            items.append(item)
    return items


def load_json(path: str) -> Any:
    """Helper for tests / local snapshots of MCP responses."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
