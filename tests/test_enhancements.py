import random
from pathlib import Path
from dataclasses import replace
import pytest
from mcopt.models import Item, UserNeed
from mcopt.presentation import explanation, compromises, draw_with_history
from mcopt.scoring import utility, passes_hard_constraints
from mcopt.group import group_score
from mcopt.live_data import refresh, snapshot, MCPClient, convert

FIXTURES = Path(__file__).parent / 'fixtures'


def test_explanation_exactly_reconstructs_custom_utility():
    items = snapshot(FIXTURES).items
    need = UserNeed(30)
    weights = (.2, .55, .15, .1)
    for item in items:
        assert sum(r['contribution'] for r in explanation(item, need, items, weights)) == pytest.approx(utility(item, need, items, weights))


def test_compromises_minimum_each_direction_and_never_relax_dislikes():
    items = [Item('cheap', 12, 90, 10, 'a'), Item('costly', 15, 90, 10, 'a'),
             Item('hot', 8, 120, 10, 'a'), Item('both', 11, 110, 10, 'a'),
             Item('forbidden', 10, 100, 10, 'a', tags=('fish',))]
    members = [UserNeed(10, max_calories=100, disliked_tags=('fish',)), UserNeed(20)]
    choices = compromises(items, members)
    assert {s.item.name for s in choices} == {'cheap', 'hot', 'both'}
    for s in choices:
        assert all(passes_hard_constraints(s.item, m) for m in s.members)
        assert s.group_score == pytest.approx(group_score(s.member_scores))
    assert members[0].budget == 10 and members[0].max_calories == 100
    assert compromises([items[-1]], members) == []


def test_blind_history_avoids_three_and_preserves_catalog_normalization():
    items = snapshot(FIXTURES).items
    need = UserNeed(30)
    history = [i.name for i in items[:3]]
    result, fallback = draw_with_history(items, need, 'balanced', history, rng=random.Random(1))
    assert not fallback and result.item.name not in history
    assert sum(result.probabilities.values()) == pytest.approx(1)
    assert not set(history) & set(result.probabilities)
    result, fallback = draw_with_history(items[:2], need, 'balanced', history, rng=random.Random(1))
    assert fallback and result.item is not None
    result, fallback = draw_with_history(items, UserNeed(0), 'balanced', history)
    assert result.item is None and not fallback


def test_exploration_modes_raise_unseen_probability():
    items = [Item('familiar', 10, 400, 30, 'burger', tags=('beef',)),
             Item('new', 10, 100, 5, 'side', tags=('corn',))]
    need = UserNeed(30, preferred_tags=('beef',))
    probabilities = []
    for mode in ('conservative', 'balanced', 'adventurous'):
        result, _ = draw_with_history(items, need, mode, ['familiar']*3, False, random.Random(0))
        probabilities.append(result.probabilities['new'])
    assert probabilities[0] < probabilities[1] < probabilities[2]


def test_refresh_success_and_atomic_fallback():
    from mcopt.mcp_adapter import load_json
    calls = []
    class Fake:
        def initialize(self): pass
        def call(self, name, args):
            calls.append((name, args))
            return load_json(str(FIXTURES / ('mcp_meals_min.json' if name == 'query-meals' else 'mcp_nutrition_min.json')))
    data = refresh(FIXTURES, 'TEST', Fake)
    assert data.source.startswith('实时 MCP') and len(data.items) == 6
    assert [c[0] for c in calls] == ['query-meals', 'list-nutrition-foods']
    assert calls[0][1] == {'storeCode': 'TEST', 'orderType': 1}
    class Broken(Fake):
        def call(self, name, args): raise RuntimeError('SECRET_TOKEN')
    data = refresh(FIXTURES, 'TEST', Broken)
    assert data.source.startswith('本地快照') and 'SECRET' not in repr(data)
    assert refresh(FIXTURES, '').source.startswith('本地快照')
    with pytest.raises(ValueError): MCPClient('fake').call('create-order', {})


def test_invalid_live_data_is_rejected():
    with pytest.raises(ValueError): convert({'success': False}, {}, 'live')
    with pytest.raises(ValueError): convert({}, {}, 'live')


def test_streamlit_all_tabs_history_and_compromise():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    assert not app.exception
    app.button[1].click().run()
    assert not app.exception
    app.number_input(key='group_budget_0').set_value(0)
    app.button(key='group_recommend').click().run()
    assert not app.exception
    assert any('放宽 →' in x.label for x in app.expander)
    draw = next(b for b in app.button if b.label == '抽取盲盒 🎁')
    draw.click().run()
    assert not app.exception and len(app.session_state['blind_history']) == 1
    first = app.session_state['blind_history'][0]
    next(b for b in app.button if b.label == '抽取盲盒 🎁').click().run()
    assert not app.exception and app.session_state['blind_history'][-1] != first
    next(b for b in app.button if b.label == '清空盲盒历史').click().run()
    assert app.session_state['blind_history'] == []
    next(t for t in app.text_input if t.label == "门店编码（storeCode）").set_value("")
    app.button[0].click().run()
    assert not app.exception and app.session_state['menu_data'].source.startswith('本地快照')
