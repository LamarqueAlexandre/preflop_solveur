"""Tests for the node views shown by the interface (FR-021, US1 scenario 4, US2 scenario 4).

The reference game and its values are computed by hand in docs/notes/vues-noeud.md.
"""

import math
from types import MappingProxyType

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.cards import N_COMBOS
from engine.game import (
    ROOT_ID,
    Action,
    ActionKind,
    GameConfig,
    GameTree,
    Node,
    Position,
    TerminalKind,
    build_tree,
)
from engine.library import (
    Solution,
    SolutionSummary,
    SolveParams,
    nearest_solution,
    node_summary,
    solve,
    terminal_view,
)
from engine.library.solution import engine_version
from engine.realization import default_profile
from engine.solver import EquityTables, TerminalValues, exploitability, node_values


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


# --- Reference game: values computed by hand ---------------------------------------------


def push_fold_tree(stack: float) -> GameTree:
    """SB pushes or folds, BB calls or folds; the BTN has folded before the root."""
    fold = Action(ActionKind.FOLD, 0.0)
    folded_btn = (True, False, False)

    def node(
        node_id: str,
        actor: Position | None,
        actions: tuple[Action, ...],
        children: tuple[str, ...],
        contributions: tuple[float, float, float],
        folded: tuple[bool, bool, bool],
        level: int,
        terminal: TerminalKind | None,
    ) -> Node:
        stacks = (stack - contributions[0], stack - contributions[1], stack - contributions[2])
        return Node(
            node_id, actor, actions, children, contributions, stacks, folded, level, terminal
        )

    push = Action(ActionKind.ALL_IN, stack)
    nodes = [
        node(ROOT_ID, Position.SB, (fold, push), ("F", "A"), (0, 0.5, 1), folded_btn, 0, None),
        node("F", None, (), (), (0, 0.5, 1), (True, True, False), 0, TerminalKind.FOLD),
        node(
            "A",
            Position.BB,
            (fold, Action(ActionKind.CALL, stack)),
            ("A-F", "A-C"),
            (0, stack, 1),
            folded_btn,
            1,
            None,
        ),
        node("A-F", None, (), (), (0, stack, 1), (True, False, True), 1, TerminalKind.FOLD),
        node("A-C", None, (), (), (0, stack, stack), folded_btn, 1, TerminalKind.SHOWDOWN),
    ]
    return GameTree(
        config=GameConfig.equal_stacks(stack), nodes=MappingProxyType({n.id: n for n in nodes})
    )


def strategy(strong: list[float], weak: list[float]) -> np.ndarray:
    return np.array([strong, weak]).T


# SB: STRONG always pushes, WEAK pushes 25%. BB: STRONG calls, WEAK folds.
PROFILE = {ROOT_ID: strategy([0.0, 1.0], [0.75, 0.25]), "A": strategy([0.0, 1.0], [1.0, 0.0])}
# SB never pushes: node A and its children are never reached.
NEVER_PUSH = {ROOT_ID: strategy([1.0, 0.0], [1.0, 0.0]), "A": strategy([0.0, 1.0], [1.0, 0.0])}


def toy_solution(profile: dict[str, np.ndarray] = PROFILE) -> Solution:
    tree = push_fold_tree(10.0)
    tables = strength_tables([3.0, 1.0])
    values = TerminalValues(tree, tables, default_profile())
    return Solution(
        tree=tree,
        profile=default_profile(),
        params=SolveParams(),
        iterations=0,
        duration_seconds=0.0,
        exploitability=exploitability(tree, values, profile),
        strategy=profile,
        values=node_values(tree, values, profile),
        hand_mass=values.hand_mass(),
        engine_version=engine_version(),
        equity_digest=tables.digest,
    )


# --- Node summary (FR-021) ---------------------------------------------------------------


def test_root_summary_weights_hands_by_how_often_they_are_there() -> None:
    """SB at the root: weights 4 / 4, fold = (4·0 + 4·0.75) / 8 = 0.375."""
    summary = node_summary(toy_solution(), ROOT_ID)
    assert summary.node_id == ROOT_ID
    assert summary.actor is Position.SB
    assert summary.reached
    assert summary.frequencies == pytest.approx((0.375, 0.625))
    assert summary.pot == pytest.approx(1.5)


def test_summary_facing_the_push() -> None:
    """BB at A: weights 2.5 / 2.5, STRONG calls, WEAK folds: 50 / 50."""
    summary = node_summary(toy_solution(), "A")
    assert summary.actor is Position.BB
    assert summary.frequencies == pytest.approx((0.5, 0.5))
    assert summary.pot == pytest.approx(11.0)


def test_range_fractions_follow_the_previous_actions() -> None:
    """At A, the SB range is STRONG 1 + WEAK 0.25 out of 2 classes of equal mass: 62.5%."""
    summary = node_summary(toy_solution(), "A")
    assert summary.range_fraction[Position.SB] == pytest.approx(0.625)
    assert summary.range_fraction[Position.BB] == pytest.approx(1.0)
    assert summary.range_combos[Position.SB] == pytest.approx(0.625 * N_COMBOS)


def test_unreached_node_has_no_frequencies() -> None:
    summary = node_summary(toy_solution(NEVER_PUSH), "A")
    assert not summary.reached
    assert summary.frequencies is None
    assert summary.range_fraction[Position.SB] == 0.0


def test_summary_of_a_terminal_is_refused() -> None:
    with pytest.raises(ValueError):
        node_summary(toy_solution(), "A-C")


def test_summary_of_an_unknown_node_is_refused() -> None:
    with pytest.raises(KeyError):
        node_summary(toy_solution(), "R99")


@pytest.fixture(scope="module")
def solved() -> Solution:
    tree = build_tree(GameConfig.equal_stacks(12.0))
    tables = strength_tables([3.0, 1.0, 2.0, 0.7])
    return solve(tree, tables, default_profile(), SolveParams(max_iterations=200))


@settings(max_examples=30, deadline=None)
@given(data=st.data())
def test_summaries_are_distributions_on_a_solved_tree(
    solved: Solution, data: st.DataObject
) -> None:
    decisions = [node.id for node in solved.tree if not node.is_terminal]
    node_id = data.draw(st.sampled_from(decisions))
    summary = node_summary(solved, node_id)
    for fraction in summary.range_fraction:
        assert -1e-12 <= fraction <= 1 + 1e-12
    if summary.reached:
        assert summary.frequencies is not None
        assert len(summary.frequencies) == len(solved.tree.node(node_id).actions)
        assert all(f >= -1e-12 for f in summary.frequencies)
        assert sum(summary.frequencies) == pytest.approx(1.0)


# --- Terminal view (US2 scenario 4) ------------------------------------------------------


def test_showdown_terminal() -> None:
    """A-C: SB weights STRONG 2 / WEAK 0.5, EV 0 / -5: mean -1. BB: +1. BTN folded: 0."""
    view = terminal_view(toy_solution(), "A-C")
    assert view.kind is TerminalKind.SHOWDOWN
    assert view.reached
    assert view.pot == pytest.approx(20.0)
    assert view.contributions == pytest.approx((0.0, 10.0, 10.0))
    assert view.folded == (True, False, False)
    assert view.ev == pytest.approx((0.0, -1.0, 1.0))


def test_fold_terminal() -> None:
    """A-F: the SB wins the 11bb pot with 10bb in it (+1), the BB loses its blind."""
    view = terminal_view(toy_solution(), "A-F")
    assert view.kind is TerminalKind.FOLD
    assert view.ev == pytest.approx((0.0, 1.0, -1.0))


def test_unreached_terminal_has_no_ev() -> None:
    view = terminal_view(toy_solution(NEVER_PUSH), "A-C")
    assert not view.reached
    assert view.ev == (None, None, None)


def test_terminal_view_of_a_decision_node_is_refused() -> None:
    with pytest.raises(ValueError):
        terminal_view(toy_solution(), "A")


# --- Nearest available depth (US1 scenario 4, D-018) -------------------------------------


def summary(
    stack: float, fingerprint: str | None = None, created_at: str = "2026-11-01"
) -> SolutionSummary:
    return SolutionSummary(
        fingerprint=fingerprint or f"fp-{stack}",
        stacks=(stack, stack, stack),
        tranche="t",
        profile_name="default",
        profile_version="1",
        engine_version="0.1.0",
        format_version=1,
        nash_conv_percent=0.1,
        publishable=True,
        iterations=100,
        created_at=created_at,
    )


LIBRARY = [summary(10.0), summary(13.0), summary(15.0), summary(20.0)]


def test_exact_depth_is_found() -> None:
    found = nearest_solution(LIBRARY, 15.0)
    assert found is not None
    assert found.exact
    assert found.summary.fingerprint == "fp-15.0"


@pytest.mark.parametrize(("stack", "expected"), [(12.0, 13.0), (17.0, 15.0), (3.0, 10.0)])
def test_missing_depth_gives_the_nearest(stack: float, expected: float) -> None:
    found = nearest_solution(LIBRARY, stack)
    assert found is not None
    assert not found.exact
    assert found.summary.stacks[0] == expected


def test_tie_goes_to_the_lower_depth() -> None:
    found = nearest_solution(LIBRARY, 14.0)
    assert found is not None
    assert found.summary.stacks[0] == 13.0


def test_several_solutions_at_one_depth_gives_the_most_recent() -> None:
    library = [summary(15.0, "old", "2026-11-01"), summary(15.0, "new", "2026-11-20")]
    found = nearest_solution(library, 15.0)
    assert found is not None
    assert found.summary.fingerprint == "new"


def test_empty_library_gives_nothing() -> None:
    assert nearest_solution([], 15.0) is None


@pytest.mark.parametrize("stack", [0.0, -3.0, math.nan, math.inf])
def test_invalid_depth_is_refused(stack: float) -> None:
    with pytest.raises(ValueError):
        nearest_solution(LIBRARY, stack)
