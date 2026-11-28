"""Tests for the training engine: spot types, drawing, grading, session summary (US4, D-008).

The reference game and its sampling weights are computed by hand in
docs/notes/entrainement.md.
"""

from collections import Counter
from types import MappingProxyType

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from engine.cards import CLASS_OF_COMBO, COMBOS
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
from engine.library import Solution, SolveParams, solution_fingerprint, solve
from engine.library.solution import engine_version
from engine.realization import default_profile
from engine.solver import EquityTables, TerminalValues, exploitability, node_values
from engine.training import (
    Answer,
    Grade,
    GradingThresholds,
    SpotFilters,
    SpotType,
    draw_spots,
    grade,
    spot_type,
    summarize,
)

STRONG, WEAK = 0, 1


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


# --- Spot types --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stack", "node_id", "expected"),
    [
        (12.0, ROOT_ID, SpotType.OPEN),  # BTN first in
        (12.0, "F", SpotType.OPEN),  # SB after a BTN fold
        (12.0, "C", SpotType.VS_LIMP),  # SB after a BTN limp
        (12.0, "F-C", SpotType.VS_LIMP),  # BB after a SB complete (check option)
        (12.0, "R2.0", SpotType.VS_RAISE),  # SB facing the BTN open
        (12.0, "A", SpotType.VS_RAISE),  # SB facing a BTN all-in
        (12.0, "F-C-R3.0", SpotType.VS_RAISE),  # SB limper facing the BB isolation
        (20.0, "R2.5-R7.5", SpotType.VS_3BET),  # BB facing an open and a 3-bet
        (20.0, "R2.5-R7.5-F", SpotType.VS_3BET),  # BTN facing the SB 3-bet
        (20.0, "R2.5-R7.5-F-A", SpotType.VS_4BET),  # SB facing the BTN 4-bet all-in
    ],
)
def test_spot_types(stack: float, node_id: str, expected: SpotType) -> None:
    tree = build_tree(GameConfig.equal_stacks(stack))
    assert spot_type(tree, tree.node(node_id)) is expected


@pytest.mark.parametrize("stack", [5.0, 12.0, 20.0])
def test_every_decision_node_has_one_type(stack: float) -> None:
    tree = build_tree(GameConfig.equal_stacks(stack))
    for node in tree:
        if node.actor is not None:
            assert isinstance(spot_type(tree, node), SpotType)
    with pytest.raises(ValueError, match="terminal"):
        spot_type(tree, next(n for n in tree if n.is_terminal))


# --- Reference game: weights computed by hand --------------------------------------------


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


PROFILE = {ROOT_ID: strategy([0.0, 1.0], [0.75, 0.25]), "A": strategy([0.0, 1.0], [1.0, 0.0])}


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


def test_spots_follow_the_real_frequencies() -> None:
    """Weights: root 4 / 4 (SB STRONG / WEAK), A 2.5 / 2.5 (BB): total 13."""
    spots = draw_spots({"toy": toy_solution()}, SpotFilters(), 20_000, seed=1)
    counts = Counter((s.node_id, s.hand_class) for s in spots)
    expected = {(ROOT_ID, STRONG): 4, (ROOT_ID, WEAK): 4, ("A", STRONG): 2.5, ("A", WEAK): 2.5}
    for key, weight in expected.items():
        assert counts[key] / len(spots) == pytest.approx(weight / 13, abs=0.015)


def test_a_spot_carries_what_the_player_sees_and_the_answer() -> None:
    (spot,) = draw_spots({"toy": toy_solution()}, SpotFilters(positions={Position.BB}), 1, 3)
    assert spot.fingerprint == "toy"
    assert spot.stack == 10.0
    assert spot.node_id == "A"
    assert spot.hero is Position.BB
    assert spot.spot_type is SpotType.VS_RAISE
    assert spot.history == ((Position.SB, Action(ActionKind.ALL_IN, 10.0)),)
    assert spot.actions == push_fold_tree(10.0).node("A").actions
    np.testing.assert_allclose(spot.strategy, PROFILE["A"][:, spot.hand_class])
    # call vs a SB pushing STRONG 100% and WEAK 25%: STRONG (0 + 0.25 * 5) / 1.25 = +1,
    # WEAK (-5 + 0.25 * 0) / 1.25 = -4
    expected_ev = {STRONG: [-1.0, 1.0], WEAK: [-1.0, -4.0]}[spot.hand_class]
    np.testing.assert_allclose(spot.action_ev, expected_ev)


def test_the_combo_belongs_to_the_class() -> None:
    tree = build_tree(GameConfig.equal_stacks(12.0))
    solution = solve(tree, strength_tables([1.0] * 169), default_profile(), SolveParams(1, 0.1, 1))
    for spot in draw_spots({"x": solution}, SpotFilters(), 200, seed=5):
        a, b = spot.cards
        assert a != b
        index = next(i for i, (x, y) in enumerate(COMBOS) if {int(x), int(y)} == {a, b})
        assert CLASS_OF_COMBO[index] == spot.hand_class
        assert len(spot.cards_text) == 4


def test_hands_that_never_reach_a_node_are_never_drawn() -> None:
    """The SB never pushes WEAK: the BB still faces a push, but the SB root spots
    for WEAK keep their weight; only weights of zero are excluded."""
    profile = {ROOT_ID: strategy([0.0, 1.0], [1.0, 0.0]), "A": strategy([0.0, 1.0], [1.0, 0.0])}
    solution = toy_solution(profile)
    for spot in draw_spots({"toy": solution}, SpotFilters(), 2_000, seed=2):
        reach = solution.values.reach_at(spot.node_id)[int(spot.hero)][spot.hand_class]
        mass = solution.values.opponent_mass_at(spot.node_id)[int(spot.hero)][spot.hand_class]
        assert reach * mass > 0


def test_same_seed_same_spots() -> None:
    solutions = {"toy": toy_solution()}
    first = draw_spots(solutions, SpotFilters(), 50, seed=7)
    again = draw_spots(solutions, SpotFilters(), 50, seed=7)
    other = draw_spots(solutions, SpotFilters(), 50, seed=8)
    key = [(s.node_id, s.hand_class, s.cards) for s in first]
    assert key == [(s.node_id, s.hand_class, s.cards) for s in again]
    assert key != [(s.node_id, s.hand_class, s.cards) for s in other]


def test_an_impossible_filter_is_reported() -> None:
    with pytest.raises(ValueError, match="no spot"):
        draw_spots({"toy": toy_solution()}, SpotFilters(positions={Position.BTN}), 5, seed=1)
    with pytest.raises(ValueError, match="no spot"):
        draw_spots({"toy": toy_solution()}, SpotFilters(min_stack=12.0), 5, seed=1)


@pytest.mark.parametrize(
    "kwargs", [{"min_stack": 10.0, "max_stack": 5.0}, {"min_stack": -1.0}, {"max_stack": 0.0}]
)
def test_invalid_filters_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        SpotFilters(**kwargs)


def test_count_must_be_positive() -> None:
    with pytest.raises(ValueError):
        draw_spots({"toy": toy_solution()}, SpotFilters(), 0, seed=1)


# --- Property: drawn spots respect the filters -------------------------------------------


@pytest.fixture(scope="module")
def library() -> dict[str, Solution]:
    tables = strength_tables([3.0, 1.0, 2.0, 0.7])
    solutions = [
        solve(build_tree(GameConfig.equal_stacks(s)), tables, default_profile(), SolveParams(40))
        for s in (5.0, 9.0, 12.0, 20.0)
    ]
    return {solution_fingerprint(s): s for s in solutions}


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    positions=st.frozensets(st.sampled_from(list(Position))),
    types=st.frozensets(st.sampled_from(list(SpotType))),
    low=st.sampled_from([None, 3.0, 5.0, 9.0, 12.5]),
    span=st.sampled_from([None, 0.0, 4.0, 10.0]),
    seed=st.integers(0, 2**32 - 1),
)
def test_drawn_spots_respect_the_filters(
    library: dict[str, Solution],
    positions: frozenset[Position],
    types: frozenset[SpotType],
    low: float | None,
    span: float | None,
    seed: int,
) -> None:
    high = None if span is None else (low or 0.0) + span
    filters = SpotFilters(positions=positions, types=types, min_stack=low, max_stack=high)
    try:
        spots = draw_spots(library, filters, 25, seed)
    except ValueError as error:
        assert "no spot" in str(error)
        return
    assert len(spots) == 25
    for spot in spots:
        assert not positions or spot.hero in positions
        assert not types or spot.spot_type in types
        assert low is None or spot.stack >= low
        assert high is None or spot.stack <= high
        solution = library[spot.fingerprint]
        assert solution.tree.node(spot.node_id).actor is spot.hero


def test_without_filters_every_depth_can_be_drawn(library: dict[str, Solution]) -> None:
    spots = draw_spots(library, SpotFilters(), 400, seed=11)
    assert {s.stack for s in spots} == {5.0, 9.0, 12.0, 20.0}


# --- Grading (D-008) ---------------------------------------------------------------------


def graded_spot(evs: list[float], frequencies: list[float]) -> object:
    """A spot whose hand has the given action EVs and equilibrium frequencies."""
    spot = draw_spots({"toy": toy_solution()}, SpotFilters(positions={Position.BB}), 1, 3)[0]
    return type(spot)(
        **{
            **spot.__dict__,
            "strategy": np.array(frequencies),
            "action_ev": np.array(evs),
        }
    )


@pytest.mark.parametrize(
    ("loss", "expected"),
    [
        (0.0, Grade.BEST),
        (0.0499, Grade.BEST),
        (0.05, Grade.INACCURACY),
        (0.2499, Grade.INACCURACY),
        (0.25, Grade.MISTAKE),
        (3.0, Grade.MISTAKE),
    ],
)
def test_grade_bounds(loss: float, expected: Grade) -> None:
    spot = graded_spot([1.0, 1.0 - loss], [1.0, 0.0])
    answer = grade(spot, 1)  # type: ignore[arg-type]
    assert answer.ev_loss == pytest.approx(loss)
    assert answer.grade is expected
    assert answer.best_action == 0


def test_custom_thresholds() -> None:
    spot = graded_spot([1.0, 0.9], [1.0, 0.0])
    thresholds = GradingThresholds(best=0.2, mistake=0.5)
    assert grade(spot, 1, thresholds).grade is Grade.BEST  # type: ignore[arg-type]
    assert grade(spot, 1, GradingThresholds(best=0.01, mistake=0.05)).grade is Grade.MISTAKE  # type: ignore[arg-type]


def test_a_mixed_action_is_correct_even_with_a_small_loss() -> None:
    """15bb, SB 88 facing R2.0: call 51% (+0.26), all-in 49% (+0.24), fold (-0.50)."""
    spot = graded_spot([-0.50, 0.26, 0.24], [0.0, 0.51, 0.49])
    shove = grade(spot, 2)  # type: ignore[arg-type]
    assert shove.grade is Grade.BEST
    assert shove.ev_loss == pytest.approx(0.02)
    assert shove.frequency == pytest.approx(0.49)
    fold = grade(spot, 0)  # type: ignore[arg-type]
    assert fold.grade is Grade.MISTAKE
    assert fold.ev_loss == pytest.approx(0.76)


def test_a_frequency_below_the_mixed_threshold_is_graded_on_its_loss() -> None:
    spot = graded_spot([1.0, 0.6], [0.995, 0.005])
    assert grade(spot, 1).grade is Grade.MISTAKE  # type: ignore[arg-type]
    assert grade(spot, 1, GradingThresholds(mixed_frequency=0.001)).grade is Grade.BEST  # type: ignore[arg-type]


@pytest.mark.parametrize("action", [-1, 2])
def test_an_unknown_action_is_rejected(action: int) -> None:
    with pytest.raises(ValueError):
        grade(graded_spot([1.0, 0.0], [1.0, 0.0]), action)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"best": 0.0},
        {"best": 0.3, "mistake": 0.2},
        {"mixed_frequency": -0.1},
        {"mixed_frequency": 1.5},
    ],
)
def test_invalid_thresholds_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        GradingThresholds(**kwargs)


def test_default_thresholds_follow_d008() -> None:
    thresholds = GradingThresholds()
    assert (thresholds.best, thresholds.mistake, thresholds.mixed_frequency) == (0.05, 0.25, 0.01)


# --- Session summary ---------------------------------------------------------------------


def test_summary_of_a_session() -> None:
    spot = graded_spot([1.0, 0.9, 0.0], [1.0, 0.0, 0.0])
    answers = [grade(spot, a) for a in (0, 0, 1, 2)]  # type: ignore[arg-type]
    summary = summarize(answers)
    assert summary.count == 4
    assert (summary.best, summary.inaccuracies, summary.mistakes) == (2, 1, 1)
    assert summary.score == pytest.approx(0.5)
    assert summary.total_loss == pytest.approx(1.1)
    assert summary.mean_loss == pytest.approx(0.275)
    assert summary.errors == (answers[2], answers[3])
    assert all(isinstance(a, Answer) for a in summary.errors)


def test_summary_of_an_empty_session() -> None:
    summary = summarize([])
    assert summary.count == 0
    assert summary.score == summary.total_loss == summary.mean_loss == 0.0
    assert summary.errors == ()
