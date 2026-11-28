"""Tests for the realization-profile sensitivity test (FR-008a, SC-009).

The comparison numbers on the push/fold reference game are computed by hand
in docs/notes/sensibilite-realisation.md.
"""

from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pytest

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
from engine.game.config import Tranche
from engine.library import (
    FileSolutionStore,
    SolveParams,
    engine_version,
    fingerprint,
)
from engine.library import batch as batch_module
from engine.library.sensitivity import (
    MODES,
    compare_strategies,
    perturb_profile,
    render_report,
    run_sensitivity,
)
from engine.realization import FlopPosition, PotType, RealizationKey, default_profile
from engine.solver import EquityTables, TerminalValues, node_values

STRONG, WEAK = 0, 1


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


# --- Profile variants --------------------------------------------------------------------


def key(players: int, position: FlopPosition) -> RealizationKey:
    return RealizationKey(players, PotType.RAISED, Tranche.MEDIUM, position)


@pytest.mark.parametrize(
    ("mode", "ip", "oop", "first", "middle", "last"),
    [
        ("U+", 1.15, 1.05, 1.03, 1.08, 1.16),
        ("U-", 0.95, 0.85, 0.83, 0.88, 0.96),
        ("E+", 1.15, 0.85, 0.83, 0.98, 1.16),
        ("E-", 0.95, 1.05, 1.03, 0.98, 0.96),
    ],
)
def test_perturbed_factors(
    mode: str, ip: float, oop: float, first: float, middle: float, last: float
) -> None:
    """Default (raised pot, 9-15bb): IP 1.05, OOP 0.95, first 0.93, middle 0.98, last 1.06."""
    profile = perturb_profile(default_profile(), mode, 0.1)
    expected = {
        key(2, FlopPosition.IP): ip,
        key(2, FlopPosition.OOP): oop,
        key(3, FlopPosition.FIRST): first,
        key(3, FlopPosition.MIDDLE): middle,
        key(3, FlopPosition.LAST): last,
    }
    for context, factor in expected.items():
        assert profile.factor(context) == pytest.approx(factor)
    assert set(profile.factors) == set(default_profile().factors)


def test_perturbed_profile_is_renamed() -> None:
    base = default_profile()
    profile = perturb_profile(base, "E+", 0.1)
    assert profile.name == "default~E+0.1"
    assert profile.version == base.version
    tree = build_tree(GameConfig.equal_stacks(12.0))
    params, digest = SolveParams(), "ab" * 32
    assert fingerprint(tree, profile, params, digest, engine_version()) != fingerprint(
        tree, base, params, digest, engine_version()
    )


def test_modes_are_the_four_variants() -> None:
    assert MODES == ("U+", "U-", "E+", "E-")


@pytest.mark.parametrize(("mode", "delta"), [("X+", 0.1), ("E+", 0.0), ("E+", -0.1)])
def test_invalid_variants_are_rejected(mode: str, delta: float) -> None:
    with pytest.raises(ValueError):
        perturb_profile(default_profile(), mode, delta)


def test_a_non_positive_factor_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        perturb_profile(default_profile(), "E+", 1.0)


# --- Comparison on the reference game, computed by hand ----------------------------------


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
        terminal: TerminalKind | None,
    ) -> Node:
        stacks = (stack - contributions[0], stack - contributions[1], stack - contributions[2])
        return Node(node_id, actor, actions, children, contributions, stacks, folded, 0, terminal)

    nodes = [
        node(
            ROOT_ID,
            Position.SB,
            (fold, Action(ActionKind.ALL_IN, stack)),
            ("F", "A"),
            (0.0, 0.5, 1.0),
            folded_btn,
            None,
        ),
        node("F", None, (), (), (0.0, 0.5, 1.0), (True, True, False), TerminalKind.FOLD),
        node(
            "A",
            Position.BB,
            (fold, Action(ActionKind.CALL, stack)),
            ("A-F", "A-C"),
            (0.0, stack, 1.0),
            folded_btn,
            None,
        ),
        node("A-F", None, (), (), (0.0, stack, 1.0), (True, False, True), TerminalKind.FOLD),
        node("A-C", None, (), (), (0.0, stack, stack), folded_btn, TerminalKind.SHOWDOWN),
    ]
    return GameTree(
        config=GameConfig.equal_stacks(stack), nodes=MappingProxyType({n.id: n for n in nodes})
    )


def strategy(strong: list[float], weak: list[float]) -> np.ndarray:
    return np.array([strong, weak]).T


BASE = {ROOT_ID: strategy([0.0, 1.0], [0.75, 0.25]), "A": strategy([0.0, 1.0], [1.0, 0.0])}
VARIANT = {ROOT_ID: strategy([0.0, 1.0], [0.25, 0.75]), "A": strategy([0.0, 1.0], [0.4, 0.6])}


def toy_comparison(base: Any = BASE, variant: Any = VARIANT, min_reach: float = 0.01) -> Any:
    tree = push_fold_tree(10.0)
    values = TerminalValues(tree, strength_tables([3.0, 1.0]), default_profile())
    return compare_strategies(
        tree, base, variant, node_values(tree, values, base), values.hand_mass(), min_reach
    )


def test_gaps_per_node() -> None:
    """Root: WEAK moves 0.5 of its strategy; A: WEAK moves 0.6 (see the note)."""
    comparison = toy_comparison()
    root, facing = comparison.nodes
    assert (root.node_id, root.actor) == (ROOT_ID, Position.SB)
    assert root.reach_probability == pytest.approx(1.0)
    assert root.mean_gap == pytest.approx(0.25)
    assert root.max_gap == pytest.approx(0.5)
    assert root.changed == (WEAK,)
    assert (facing.node_id, facing.actor) == ("A", Position.BB)
    assert facing.reach_probability == pytest.approx(0.625)
    assert facing.mean_gap == pytest.approx(0.3)
    assert facing.max_gap == pytest.approx(0.6)
    assert facing.changed == (WEAK,)
    assert comparison.mean_gap == pytest.approx((0.25 + 0.625 * 0.3) / 1.625)


def test_identical_strategies_give_no_gap() -> None:
    comparison = toy_comparison(BASE, BASE)
    assert comparison.mean_gap == 0.0
    for node in comparison.nodes:
        assert node.mean_gap == node.max_gap == 0.0
        assert node.changed == ()


def test_hands_below_the_minimum_reach_are_ignored_for_max_and_changes() -> None:
    """At 5bb, the BTN limps class 0 with 0.5% only: its strategy at C-F-A hardly matters."""
    tree = build_tree(GameConfig.equal_stacks(5.0))
    n = 2
    values = TerminalValues(tree, strength_tables([3.0, 1.0]), default_profile())
    base = {
        node.id: np.full((len(node.actions), n), 1.0 / len(node.actions))
        for node in tree
        if not node.is_terminal
    }
    root = np.zeros((len(tree.root.actions), n))
    root[0] = [0.995, 0.5]  # fold
    root[1] = [0.005, 0.5]  # limp
    base[ROOT_ID] = root
    variant = dict(base)
    variant["C-F-A"] = np.array([[1.0, 0.5], [0.0, 0.5]])  # class 0 now folds 100%
    base["C-F-A"] = np.array([[0.0, 0.5], [1.0, 0.5]])
    comparison = compare_strategies(
        tree, base, variant, node_values(tree, values, base), values.hand_mass(), 0.01
    )
    node = next(n for n in comparison.nodes if n.node_id == "C-F-A")
    assert node.max_gap == 0.0
    assert node.changed == ()
    assert 0.0 < node.mean_gap < 1.0


def test_trees_must_match() -> None:
    tree = push_fold_tree(10.0)
    values = TerminalValues(tree, strength_tables([3.0, 1.0]), default_profile())
    with pytest.raises(ValueError, match="node"):
        compare_strategies(
            tree,
            BASE,
            {ROOT_ID: BASE[ROOT_ID]},
            node_values(tree, values, BASE),
            values.hand_mass(),
            0.01,
        )


# --- Orchestration -----------------------------------------------------------------------


TABLES = strength_tables([3.0, 1.0, 2.0, 0.7])
PARAMS = SolveParams(max_iterations=40, check_every=20)


def test_run_sensitivity_compares_every_depth_and_mode(tmp_path: Path) -> None:
    base_store = FileSolutionStore(tmp_path / "solutions")
    store = FileSolutionStore(tmp_path / "sensitivity")
    results = run_sensitivity(
        (5.0, 12.0), ("E+", "U-"), 0.1, TABLES, default_profile(), PARAMS, base_store, store
    )
    assert [(r.stack, r.mode) for r in results] == [
        (5.0, "E+"),
        (5.0, "U-"),
        (12.0, "E+"),
        (12.0, "U-"),
    ]
    assert len(base_store.list_solutions()) == 2
    assert {s.profile_name for s in store.list_solutions()} == {"default~E+0.1", "default~U-0.1"}
    for result in results:
        assert 0.0 <= result.comparison.mean_gap <= 1.0
        assert len(result.base_root_ev) == len(result.variant_root_ev) == 3


def test_a_rerun_solves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stores = (FileSolutionStore(tmp_path / "a"), FileSolutionStore(tmp_path / "b"))
    first = run_sensitivity((5.0,), ("E+",), 0.1, TABLES, default_profile(), PARAMS, *stores)

    def no_solve(*args: object, **kwargs: object) -> None:
        raise AssertionError("solve must not be called")

    monkeypatch.setattr(batch_module, "solve", no_solve)
    second = run_sensitivity((5.0,), ("E+",), 0.1, TABLES, default_profile(), PARAMS, *stores)
    assert second[0].comparison.mean_gap == first[0].comparison.mean_gap


def test_report_is_markdown_with_one_section_per_depth(tmp_path: Path) -> None:
    stores = (FileSolutionStore(tmp_path / "a"), FileSolutionStore(tmp_path / "b"))
    results = run_sensitivity(
        (5.0, 12.0), ("E+", "E-"), 0.1, TABLES, default_profile(), PARAMS, *stores
    )
    report = render_report(results, lambda c: f"h{c}")
    assert report.startswith("#")
    assert "## 5bb" in report and "## 12bb" in report
    assert "E+" in report and "E-" in report
    assert "relatif au modèle" in report
