import re
import sys
from dataclasses import replace
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mcopt.mcp_adapter import (
    items_from_mcp, load_json, match_nutrition, parse_nutrition_foods,
)
from mcopt.blind_box import BlindBoxMode, recommend_blind_box
from mcopt.group import recommend_group
from mcopt.models import UserNeed
from mcopt.personal import recommend_personal
from mcopt.scoring import DEFAULT_WEIGHTS
from mcopt.presentation import explanation, compromises, draw_with_history
from mcopt.live_data import snapshot, refresh
from mcopt.blind_box import novelty_score, diversity_score


def keywords(text):
    return tuple(dict.fromkeys(
        token.casefold() for token in re.split(r"[\s,，、;；/]+", text.strip()) if token
    ))


def matches_keyword(item, keyword):
    # Match individual names/tags, not broad categories such as 牛鱼肉堡.
    aliases = {
        "鸡肉": ("鸡",), "chicken": ("鸡",),
        "牛肉": ("牛肉",), "beef": ("牛肉",),
        "汉堡": ("汉堡", "堡", "巨无霸"), "burger": ("汉堡", "堡", "巨无霸"),
        "芝士": ("芝士", "吉士"), "cheese": ("芝士", "吉士"),
        "鱼": ("鱼",), "fish": ("鱼",),
        "辣": ("辣",), "spicy": ("辣",),
    }
    terms = aliases.get(keyword, (keyword,))
    labels = (item.name.casefold(), *(tag.casefold() for tag in item.tags))
    return any(term in label for term in terms for label in labels)


def load_personal_menu():
    data = st.session_state.menu_data
    return list(data.items), list(data.missing)


def explain(item, need, catalog, weights=DEFAULT_WEIGHTS):
    rows = explanation(item, need, catalog, weights)
    labels = dict(preference="口味匹配", nutrition="营养表现", value="性价比", discount="优惠")
    st.caption("为什么推荐它？")
    st.table([{"分项": labels[r["component"]], "分数": round(r["score"], 4),
               "权重": f'{r["weight"]:.0%}', "加权贡献": round(r["contribution"], 4)} for r in rows])
    st.caption(f"Utility：{sum(r['contribution'] for r in rows):.4f} · 满足预算 ¥{need.budget:g}"
               + (f" · 满足热量上限 {need.max_calories:g} kcal" if need.max_calories is not None else ""))
    hits = need.preferred_set() & item.tag_set()
    if hits:
        st.caption("命中偏好：" + "、".join(sorted(hits)))


def group_details(item, scores, score, members, catalog):
    st.table([{"成员": f"成员 {i + 1}", "满意度": round(v, 4)} for i, v in enumerate(scores)])
    a, b, c = st.columns(3)
    a.metric("平均满意度", f"{sum(scores)/len(scores):.4f}")
    b.metric("最低满意度", f"{min(scores):.4f}")
    c.metric("Group score", f"{score:.4f}")
    st.caption("Group score = 0.6 × 平均满意度 + 0.4 × 最低满意度。满意度为模型分数。")
    for i, member in enumerate(members):
        with st.expander(f"成员 {i + 1} 推荐理由"):
            explain(item, member, catalog)


def source_caption():
    data = st.session_state.menu_data
    st.caption(f"数据源：{data.source} · 载入时间（北京时间）：{data.timestamp}")


st.set_page_config(
    page_title="McOpt-X",
    page_icon="🍔",
    layout="wide",
)

st.title("McOpt-X")
st.caption("McDonald's Intelligent Decision System")

fixtures = ROOT / "tests" / "fixtures"
if "menu_data" not in st.session_state:
    try:
        st.session_state.menu_data = snapshot(fixtures)
    except Exception:
        st.error("本地快照不可用，请检查 tests/fixtures 中的菜单和营养文件。")
        st.stop()
st.session_state.setdefault("blind_history", [])
with st.sidebar:
    st.subheader("菜单数据")
    store_code = st.text_input("门店编码（storeCode）", value="3390143", help="实时菜单查询必填，使用到店自取场景。")
    if st.button("刷新真实麦当劳数据"):
        with st.spinner("正在查询菜单和营养…"):
            try:
                st.session_state.menu_data = refresh(fixtures, store_code)
                st.session_state.pop("blind_last", None)
            except Exception:
                st.error("实时数据及本地快照均不可用，保留上次数据。")
    source_caption()
    if st.session_state.menu_data.notice:
        st.warning(st.session_state.menu_data.notice)
    st.caption("凭据仅从本机环境变量或 MCP 配置读取，不在页面显示。")

personal_tab, group_tab, blind_box_tab = st.tabs(
    ["🎯 Personal", "👥 Group", "🎁 Blind Box"]
)

with personal_tab:
    st.header("🎯 Personal Recommendation")
    st.write("根据你的预算、营养目标和口味偏好推荐麦当劳餐品。")

    col1, col2 = st.columns(2)

    with col1:
        budget = st.number_input(
            "预算（¥）",
            min_value=0.0,
            value=30.0,
            step=1.0,
        )

        calories = st.number_input(
            "热量上限（kcal）",
            min_value=0,
            value=800,
            step=50,
        )

    with col2:
        preferred = st.text_input(
            "喜欢的食物 / 关键词",
            placeholder="例如：鸡肉、汉堡、辣"
        )

        disliked = st.text_input(
            "不喜欢 / 忌口",
            placeholder="例如：鱼、芝士"
        )

    goal = st.selectbox(
        "本次更看重什么？",
        [
            "综合最优",
            "省钱优先",
            "营养优先",
        ],
    )

    source_caption()
    st.caption("每个方案推荐一款餐品。")
    st.caption("关键词用逗号或空格分隔，按餐品名称和标签匹配；快照不含完整配料或过敏原信息。")

    if st.button("开始推荐 🍔", type="primary"):
        try:
            items, missing = load_personal_menu()
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            st.error("菜单或营养快照读取失败，请检查 tests/fixtures 中的两个 JSON 文件。")
        else:
            if missing:
                st.info(f"当前营养数据覆盖 {len(items)} 款可推荐餐品；缺少完整营养信息的餐品已自动排除。")
            preferred_tags = keywords(preferred)
            disliked_tags = keywords(disliked)
            requested = tuple(dict.fromkeys(preferred_tags + disliked_tags))
            unmatched = [word for word in requested if not any(
                matches_keyword(item, word) for item in items
            )]
            if unmatched:
                st.warning("以下关键词未匹配到可推荐餐品：" + "、".join(unmatched))
            # Enrich copies for the existing exact-tag matching algorithm.
            items = [replace(item, tags=tuple(dict.fromkeys(
                item.tags + tuple(word for word in requested if matches_keyword(item, word))
            ))) for item in items]
            # Existing public weights are Preference / Nutrition / Value / Discount.
            weights = {
                "综合最优": DEFAULT_WEIGHTS,
                "省钱优先": (0.20, 0.10, 0.55, 0.15),
                "营养优先": (0.20, 0.55, 0.15, 0.10),
            }[goal]
            need = UserNeed(
                budget=budget,
                max_calories=calories,
                preferred_tags=preferred_tags,
                disliked_tags=disliked_tags,
                nutrition_priority=0.8 if goal == "营养优先" else 0.5,
                value_priority=0.9 if goal == "省钱优先" else 0.5,
            )
            result = recommend_personal(items, need, weights=weights)
            if not result.feasible:
                st.warning("没有符合条件的餐品，请调整预算、热量上限或忌口关键词。")
            else:
                st.success(f"找到 {len(result.feasible)} 款符合条件的餐品。")
                st.caption("所选目标影响综合排序；省钱优先侧重性价比，最低价格请看“最便宜”。三类结果可能相同。")
                for column, title, item in zip(
                    st.columns(3),
                    ("综合最优", "最便宜", "营养优先"),
                    (result.best_overall, result.cheapest, result.nutrition_first),
                ):
                    with column:
                        st.subheader(title)
                        st.write(item.name)
                        st.metric("价格", f"¥{item.effective_price:.2f}")
                        st.write(f"热量：{item.calories:g} kcal")
                        st.write(f"蛋白质：{item.protein:g} g")
                        explain(item, need, items, weights)


with group_tab:
    st.header("👥 Group Recommendation")
    st.write("为 2–6 位成员推荐同一款都能接受的餐品，每人预算按一份计算。")
    source_caption()
    st.caption("关键词按名称和标签匹配，数据不含完整配料或过敏原信息。")
    member_count = st.number_input(
        "成员人数", min_value=2, max_value=6, value=2, step=1,
        key="group_member_count",
    )
    members = []
    for index in range(member_count):
        with st.expander(f"成员 {index + 1}", expanded=True):
            left, right = st.columns(2)
            with left:
                member_budget = st.number_input(
                    "每人预算（¥）", min_value=0.0, value=30.0, step=1.0,
                    key=f"group_budget_{index}",
                )
                limit_calories = st.checkbox(
                    "设置热量上限", key=f"group_limit_{index}",
                )
                member_calories = st.number_input(
                    "热量上限（kcal）", min_value=0, value=800, step=50,
                    disabled=not limit_calories, key=f"group_calories_{index}",
                )
            with right:
                member_preferred = st.text_input(
                    "喜欢的食物 / 关键词", placeholder="例如：鸡肉、汉堡、辣",
                    key=f"group_preferred_{index}",
                )
                member_disliked = st.text_input(
                    "不喜欢 / 忌口", placeholder="例如：鱼、芝士",
                    key=f"group_disliked_{index}",
                )
            members.append(UserNeed(
                budget=member_budget,
                preferred_tags=keywords(member_preferred),
                disliked_tags=keywords(member_disliked),
                max_calories=member_calories if limit_calories else None,
            ))

    if st.button("开始团体推荐 🍔", type="primary", key="group_recommend"):
        try:
            items, missing = load_personal_menu()
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            st.error("菜单或营养快照读取失败，请检查 tests/fixtures 中的两个 JSON 文件。")
        else:
            if missing:
                st.info(f"当前营养数据覆盖 {len(items)} 款可推荐餐品；缺少完整营养信息的餐品已自动排除。")
            requested = tuple(dict.fromkeys(
                word for member in members
                for word in (*member.preferred_tags, *member.disliked_tags)
            ))
            unmatched = [word for word in requested if not any(
                matches_keyword(item, word) for item in items
            )]
            if unmatched:
                st.warning("以下关键词未匹配到可推荐餐品：" + "、".join(unmatched))
            items = [replace(item, tags=tuple(dict.fromkeys(
                item.tags + tuple(word for word in requested if matches_keyword(item, word))
            ))) for item in items]
            result = recommend_group(items, members)
            if result.item is None:
                st.warning("当前没有共同可行项。下面是供讨论的最小放宽候选，不会自动修改成员要求。")
                suggestions = compromises(items, members)
                st.caption("各方向分别按相对放宽总量最小排序：预算增量/原预算 + 热量增量/原上限；分母至少为 1。忌口始终保留。")
                if not suggestions:
                    st.info("仅放宽预算或热量仍无候选；当前餐品与成员忌口存在冲突，建议改为分别选餐。")
                for suggestion in suggestions:
                    with st.expander(f"{suggestion.direction}放宽 → {suggestion.item.name}", expanded=True):
                        st.write(f"¥{suggestion.item.effective_price:.2f} · {suggestion.item.calories:g} kcal · 蛋白质 {suggestion.item.protein:g} g")
                        st.table([{"成员": f"成员 {i}", "调整项": kind, "原值": old, "建议值": new}
                                  for i, kind, old, new in suggestion.changes])
                        st.caption(f"相对放宽总量：{suggestion.cost:.4f}")
                        group_details(suggestion.item, suggestion.member_scores, suggestion.group_score,
                                      suggestion.members, items)
            else:
                item = result.item
                st.subheader(item.name)
                price_col, calories_col, protein_col = st.columns(3)
                price_col.metric("每份价格", f"¥{item.effective_price:.2f}")
                calories_col.metric("每份热量", f"{item.calories:g} kcal")
                protein_col.metric("每份蛋白质", f"{item.protein:g} g")
                group_details(item, result.member_scores, result.group_score, members, items)

with blind_box_tab:
    st.header("🎁 Blind Box Recommendation")
    st.write("在预算、热量和忌口限制内，按所选模式的评分概率抽取一款餐品。")
    source_caption()
    st.caption("关键词按名称和标签匹配，数据不含完整配料或过敏原信息。")
    with st.form("blind_box_form"):
        blind_mode = st.selectbox(
            "盲盒模式", [mode.value for mode in BlindBoxMode], index=1,
            key="blind_box_mode",
        )
        st.caption("conservative：更看重效用；balanced：均衡；adventurous：更看重新颖性和多样性。")
        left, right = st.columns(2)
        with left:
            blind_budget = st.number_input(
                "预算（¥）", min_value=0.0, value=30.0, step=1.0,
                key="blind_box_budget",
            )
            blind_calories = st.number_input(
                "热量上限（kcal）", min_value=0, value=800, step=50,
                key="blind_box_calories",
            )
        with right:
            blind_preferred = st.text_input(
                "喜欢的食物 / 关键词", placeholder="例如：鸡肉、汉堡、辣",
                key="blind_box_preferred",
            )
            blind_disliked = st.text_input(
                "不喜欢 / 忌口", placeholder="例如：鱼、芝士",
                key="blind_box_disliked",
            )
        avoid_recent = st.checkbox("尽量避免最近 3 次重复", value=True)
        draw_blind_box = st.form_submit_button("抽取盲盒 🎁", type="primary")

    if draw_blind_box:
        try:
            items, missing = load_personal_menu()
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            st.error("菜单或营养快照读取失败，请检查 tests/fixtures 中的两个 JSON 文件。")
        else:
            if missing:
                st.info(f"当前营养数据覆盖 {len(items)} 款可推荐餐品；缺少完整营养信息的餐品已自动排除。")
            preferred_tags = keywords(blind_preferred)
            disliked_tags = keywords(blind_disliked)
            requested = tuple(dict.fromkeys(preferred_tags + disliked_tags))
            unmatched = [word for word in requested if not any(
                matches_keyword(item, word) for item in items
            )]
            if unmatched:
                st.warning("以下关键词未匹配到可推荐餐品：" + "、".join(unmatched))
            items = [replace(item, tags=tuple(dict.fromkeys(
                item.tags + tuple(word for word in requested if matches_keyword(item, word))
            ))) for item in items]
            need = UserNeed(
                budget=blind_budget, max_calories=blind_calories,
                preferred_tags=preferred_tags, disliked_tags=disliked_tags,
            )
            history = list(st.session_state.blind_history)
            result, repeated = draw_with_history(items, need, blind_mode, history, avoid_recent)
            if result.item is not None:
                st.session_state.blind_history = (history + [result.item.name])[-50:]
            st.session_state.blind_last = (result, repeated, history, need, items)

    if "blind_last" in st.session_state:
            result, repeated, history, need, items = st.session_state.blind_last
            if result.item is None:
                st.warning("没有符合条件的餐品，请调整预算、热量上限或忌口关键词。")
            else:
                item = result.item
                st.success(f"本次模式：{result.mode.value}；共 {len(result.feasible)} 款餐品参与抽取。")
                st.subheader(item.name)
                price_col, calories_col, protein_col = st.columns(3)
                price_col.metric("价格", f"¥{item.effective_price:.2f}")
                calories_col.metric("热量", f"{item.calories:g} kcal")
                protein_col.metric("蛋白质", f"{item.protein:g} g")
                score_col, probability_col = st.columns(2)
                score_col.metric("Blind Box score", f"{result.score:.4f}")
                probability_col.metric("本餐品抽取概率", f"{result.probabilities[item.name]:.2%}")
                st.table([
                    {"餐品": name, "抽取概率": f"{probability:.2%}"}
                    for name, probability in result.probabilities.items()
                ])
                explain(item, need, items)
                history_items = [i for name in history for i in items if i.name == name]
                st.caption(f"新颖性：{novelty_score(item, history, items):.4f} · 多样性：{diversity_score(item, history_items, items):.4f}")
                st.caption("效用 / 新颖性 / 多样性权重：conservative 70/20/10；balanced 50/30/20；adventurous 30/40/30。概率为避重后的条件概率。")
                if repeated:
                    st.info("所有可行餐品都在最近 3 次历史中，本次允许重复；预算、热量和忌口限制仍然有效。")
    st.caption("历史仅保存在当前会话，保留最近 50 次；重新打开会话可能重置。")
    if st.session_state.blind_history:
        st.write("最近抽取（新 → 旧）：" + " → ".join(reversed(st.session_state.blind_history[-10:])))
    if st.button("清空盲盒历史"):
        st.session_state.blind_history = []
        st.session_state.pop("blind_last", None)
        st.rerun()
