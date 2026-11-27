"""Tests for the 3-max push/fold tree (SC-002.2 and SC-002.3, D-004).

Every player pushes all-in or folds when unopened, calls or folds facing a
push; nobody re-raises and there is no limp. Node identifiers follow the full
tree (``A-C-C``...). With unequal stacks, players left with chips behind check
the hand down: the push/fold game has no postflop betting.
"""

import pytest

from engine.game import (
    ROOT_ID,
    Action,
    ActionKind,
    GameConfig,
    Position,
    TerminalKind,
    build_push_fold_tree,
)

PUSH_OR_FOLD = [ActionKind.FOLD, ActionKind.ALL_IN]
CALL_OR_FOLD = [ActionKind.FOLD, ActionKind.CALL]


def kinds(actions: tuple[Action, ...]) -> list[ActionKind]:
    return [action.kind for action in actions]


# --- Structure -----------------------------------------------------------------------------


def test_nodes_in_depth_first_order() -> None:
    tree = build_push_fold_tree(GameConfig.equal_stacks(10.0))
    assert [node.id for node in tree] == [
        ROOT_ID,
        "F",
        "F-F",
        "F-A",
        "F-A-F",
        "F-A-C",
        "A",
        "A-F",
        "A-F-F",
        "A-F-C",
        "A-C",
        "A-C-F",
        "A-C-C",
    ]


@pytest.mark.parametrize(
    ("node_id", "actor", "action_kinds", "contributions", "folded", "raise_level"),
    [
        (ROOT_ID, Position.BTN, PUSH_OR_FOLD, (0.0, 0.5, 1.0), (False, False, False), 0),
        ("F", Position.SB, PUSH_OR_FOLD, (0.0, 0.5, 1.0), (True, False, False), 0),
        ("F-A", Position.BB, CALL_OR_FOLD, (0.0, 10.0, 1.0), (True, False, False), 1),
        ("A", Position.SB, CALL_OR_FOLD, (10.0, 0.5, 1.0), (False, False, False), 1),
        ("A-F", Position.BB, CALL_OR_FOLD, (10.0, 0.5, 1.0), (False, True, False), 1),
        ("A-C", Position.BB, CALL_OR_FOLD, (10.0, 10.0, 1.0), (False, False, False), 1),
    ],
)
def test_decision_nodes(
    node_id: str,
    actor: Position,
    action_kinds: list[ActionKind],
    contributions: tuple[float, float, float],
    folded: tuple[bool, bool, bool],
    raise_level: int,
) -> None:
    node = build_push_fold_tree(GameConfig.equal_stacks(10.0)).node(node_id)
    assert node.actor is actor
    assert kinds(node.actions) == action_kinds
    assert node.actions[1].amount == 10.0
    assert node.contributions == contributions
    assert node.folded == folded
    assert node.raise_level == raise_level
    prefix = "" if node_id == ROOT_ID else f"{node_id}-"
    assert node.children == (f"{prefix}F", f"{prefix}{node.actions[1].token}")


@pytest.mark.parametrize(
    ("node_id", "terminal", "contributions", "folded"),
    [
        ("F-F", TerminalKind.FOLD, (0.0, 0.5, 1.0), (True, True, False)),
        ("F-A-F", TerminalKind.FOLD, (0.0, 10.0, 1.0), (True, False, True)),
        ("F-A-C", TerminalKind.SHOWDOWN, (0.0, 10.0, 10.0), (True, False, False)),
        ("A-F-F", TerminalKind.FOLD, (10.0, 0.5, 1.0), (False, True, True)),
        ("A-F-C", TerminalKind.SHOWDOWN, (10.0, 0.5, 10.0), (False, True, False)),
        ("A-C-F", TerminalKind.SHOWDOWN, (10.0, 10.0, 1.0), (False, False, True)),
        ("A-C-C", TerminalKind.SHOWDOWN, (10.0, 10.0, 10.0), (False, False, False)),
    ],
)
def test_terminals(
    node_id: str,
    terminal: TerminalKind,
    contributions: tuple[float, float, float],
    folded: tuple[bool, bool, bool],
) -> None:
    node = build_push_fold_tree(GameConfig.equal_stacks(10.0)).node(node_id)
    assert node.terminal is terminal
    assert node.actor is None
    assert node.actions == ()
    assert node.contributions == contributions
    assert node.folded == folded
    assert node.stacks == tuple(10.0 - c for c in contributions)


# --- Unequal stacks: calls are capped by the caller's stack -----------------------------


def test_short_sb_calls_the_btn_push_all_in() -> None:
    tree = build_push_fold_tree(GameConfig(stacks=(10.0, 6.0, 20.0)))
    assert tree.node("A").actions[1].amount == 6.0
    assert tree.node("A-C").actions[1].amount == 10.0
    showdown = tree.node("A-C-C")
    assert showdown.contributions == (10.0, 6.0, 10.0)
    assert showdown.stacks == (0.0, 0.0, 10.0)


def test_deep_callers_check_the_hand_down() -> None:
    """BTN pushes 5bb, SB and BB call with chips behind: no more betting, showdown."""
    tree = build_push_fold_tree(GameConfig(stacks=(5.0, 20.0, 20.0)))
    showdown = tree.node("A-C-C")
    assert showdown.terminal is TerminalKind.SHOWDOWN
    assert showdown.contributions == (5.0, 5.0, 5.0)
    assert showdown.stacks == (0.0, 15.0, 15.0)


def test_sb_push_is_capped_by_nothing_but_its_stack() -> None:
    tree = build_push_fold_tree(GameConfig(stacks=(10.0, 12.0, 8.0)))
    assert tree.node("F").actions[1].amount == 12.0
    assert tree.node("F-A").actions[1].amount == 8.0
    assert tree.node("F-A-C").contributions == (0.0, 12.0, 8.0)


@pytest.mark.parametrize("stacks", [(1.0, 10.0, 10.0), (10.0, 1.0, 10.0), (10.0, 10.0, 1.0)])
def test_stack_not_covering_more_than_the_big_blind_is_refused(
    stacks: tuple[float, float, float],
) -> None:
    with pytest.raises(ValueError, match="push/fold"):
        build_push_fold_tree(GameConfig(stacks=stacks))
