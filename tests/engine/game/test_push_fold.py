"""Tests for the heads-up push/fold tree (SC-002.1, D-004).

The BTN is forced to fold; the SB pushes all-in or folds; the BB calls or
folds. Node identifiers follow the full tree (``F-A-C``...), so a heads-up
strategy reads like the same line of the 3-max tree.
"""

import numpy as np
import pytest

from engine.game import (
    ROOT_ID,
    Action,
    ActionKind,
    GameConfig,
    Position,
    TerminalKind,
    build_heads_up_push_fold_tree,
)
from engine.realization import default_profile
from engine.solver import DCFRSolver, EquityTables, TerminalValues, exploitability

STRONG, WEAK = 0, 1


def kinds(actions: tuple[Action, ...]) -> list[ActionKind]:
    return [action.kind for action in actions]


# --- Structure -----------------------------------------------------------------------------


def test_nodes_in_depth_first_order() -> None:
    tree = build_heads_up_push_fold_tree(GameConfig.equal_stacks(10.0))
    assert [node.id for node in tree] == [ROOT_ID, "F", "F-F", "F-A", "F-A-F", "F-A-C"]


def test_btn_can_only_fold() -> None:
    root = build_heads_up_push_fold_tree(GameConfig.equal_stacks(10.0)).root
    assert root.actor is Position.BTN
    assert kinds(root.actions) == [ActionKind.FOLD]
    assert root.children == ("F",)


def test_sb_pushes_or_folds_without_limp() -> None:
    sb = build_heads_up_push_fold_tree(GameConfig.equal_stacks(10.0)).node("F")
    assert sb.actor is Position.SB
    assert kinds(sb.actions) == [ActionKind.FOLD, ActionKind.ALL_IN]
    assert sb.actions[1].amount == 10.0
    assert sb.folded == (True, False, False)
    assert sb.contributions == (0.0, 0.5, 1.0)


def test_bb_calls_or_folds_facing_the_push() -> None:
    bb = build_heads_up_push_fold_tree(GameConfig.equal_stacks(10.0)).node("F-A")
    assert bb.actor is Position.BB
    assert kinds(bb.actions) == [ActionKind.FOLD, ActionKind.CALL]
    assert bb.actions[1].amount == 10.0
    assert bb.contributions == (0.0, 10.0, 1.0)
    assert bb.raise_level == 1


@pytest.mark.parametrize(
    ("node_id", "terminal", "contributions", "folded"),
    [
        ("F-F", TerminalKind.FOLD, (0.0, 0.5, 1.0), (True, True, False)),
        ("F-A-F", TerminalKind.FOLD, (0.0, 10.0, 1.0), (True, False, True)),
        ("F-A-C", TerminalKind.SHOWDOWN, (0.0, 10.0, 10.0), (True, False, False)),
    ],
)
def test_terminals(
    node_id: str,
    terminal: TerminalKind,
    contributions: tuple[float, float, float],
    folded: tuple[bool, bool, bool],
) -> None:
    node = build_heads_up_push_fold_tree(GameConfig.equal_stacks(10.0)).node(node_id)
    assert node.terminal is terminal
    assert node.actor is None
    assert node.contributions == contributions
    assert node.folded == folded
    assert node.stacks == tuple(10.0 - c for c in contributions)


# --- Unequal stacks: the effective stack is put in --------------------------------------


def test_bb_shorter_than_sb_calls_all_in() -> None:
    tree = build_heads_up_push_fold_tree(GameConfig(stacks=(20.0, 10.0, 6.0)))
    assert tree.node("F-A").actions[1].amount == 6.0
    showdown = tree.node("F-A-C")
    assert showdown.contributions == (0.0, 10.0, 6.0)
    assert showdown.stacks == (20.0, 0.0, 0.0)


def test_sb_shorter_than_bb_is_called_for_its_stack() -> None:
    tree = build_heads_up_push_fold_tree(GameConfig(stacks=(20.0, 6.0, 10.0)))
    assert tree.node("F").actions[1].amount == 6.0
    showdown = tree.node("F-A-C")
    assert showdown.contributions == (0.0, 6.0, 6.0)
    assert showdown.stacks == (20.0, 0.0, 4.0)


@pytest.mark.parametrize("stacks", [(10.0, 1.0, 10.0), (10.0, 10.0, 1.0)])
def test_blind_covering_the_stack_is_refused(stacks: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError, match="push/fold"):
        build_heads_up_push_fold_tree(GameConfig(stacks=stacks))


# --- Solved by DCFR: equilibria of docs/notes/cfr.md ------------------------------------


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


@pytest.mark.parametrize(("stack", "weak_frequency"), [(3.0, 0.5), (10.0, 0.0)])
def test_dcfr_finds_the_hand_solved_equilibrium(stack: float, weak_frequency: float) -> None:
    """STRONG (75% against WEAK) always pushes and calls; WEAK does so half the time at 3bb."""
    tree = build_heads_up_push_fold_tree(GameConfig.equal_stacks(stack))
    values = TerminalValues(tree, strength_tables([3.0, 1.0]), default_profile())
    solver = DCFRSolver(tree, values)
    solver.iterate(2000)
    profile = solver.average_strategy()

    for node_id in ("F", "F-A"):
        aggressive = profile[node_id][1]
        assert aggressive[STRONG] == pytest.approx(1.0, abs=1e-2)
        assert aggressive[WEAK] == pytest.approx(weak_frequency, abs=1e-2)
    assert exploitability(tree, values, profile).percent < 0.1
