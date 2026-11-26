"""Tests for the preflop action tree, raises only (no limps yet)."""

from collections import Counter

import pytest

from engine.game import (
    ROOT_ID,
    GameConfig,
    GameTree,
    Position,
    SizingTable,
    TerminalKind,
    TrancheSizings,
    build_tree,
    default_configs,
)


def tree(stack: float) -> GameTree:
    return build_tree(GameConfig.equal_stacks(stack))


def tokens(game: GameTree, node_id: str) -> list[str]:
    return [action.token for action in game.node(node_id).actions]


def counts(game: GameTree) -> tuple[int, int]:
    decisions = sum(1 for node in game.nodes.values() if not node.is_terminal)
    return decisions, len(game.nodes) - decisions


def terminal_kinds(game: GameTree) -> Counter[TerminalKind]:
    return Counter(node.terminal for node in game.nodes.values() if node.terminal is not None)


# --- Trees counted by hand ----------------------------------------------------------------


def test_short_tree_counted_by_hand() -> None:
    # BTN: F / A. After F, SB: F / A, then BB F / C. After A, SB F / C, then BB F / C.
    game = tree(5.0)
    assert counts(game) == (6, 7)
    assert terminal_kinds(game) == {TerminalKind.FOLD: 3, TerminalKind.SHOWDOWN: 4}
    assert set(game.nodes) == {
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
    }


def test_medium_tree_counted_by_hand() -> None:
    game = tree(12.0)
    assert counts(game) == (18, 25)
    assert terminal_kinds(game) == {
        TerminalKind.FOLD: 9,
        TerminalKind.SHOWDOWN: 12,
        TerminalKind.FLOP: 4,
    }


def test_deep_tree_counted_by_hand() -> None:
    game = tree(20.0)
    assert counts(game) == (78, 115)
    assert terminal_kinds(game) == {
        TerminalKind.FOLD: 39,
        TerminalKind.SHOWDOWN: 52,
        TerminalKind.FLOP: 24,
    }


@pytest.mark.parametrize(
    ("stack", "expected"),
    [(3.0, (6, 7)), (8.0, (6, 7)), (9.0, (18, 25)), (15.0, (18, 25)), (16.0, (78, 115))],
)
def test_tranche_bounds(stack: float, expected: tuple[int, int]) -> None:
    assert counts(tree(stack)) == expected


# --- Actions by situation (FR-004, D-005) ------------------------------------------------------


def test_open_actions_by_tranche() -> None:
    assert tokens(tree(5.0), ROOT_ID) == ["F", "A"]
    assert tokens(tree(12.0), ROOT_ID) == ["F", "R2.0", "A"]
    assert tokens(tree(20.0), ROOT_ID) == ["F", "R2.0", "R2.5", "A"]


def test_sb_opens_when_btn_folds() -> None:
    game = tree(20.0)
    assert game.node("F").actor is Position.SB
    assert tokens(game, "F") == ["F", "R2.0", "R2.5", "A"]


def test_facing_a_raise_by_tranche() -> None:
    assert tokens(tree(5.0), "A") == ["F", "C"]  # every raise is all-in when short
    assert tokens(tree(12.0), "R2.0") == ["F", "C", "A"]  # 3-bet all-in
    assert tokens(tree(20.0), "R2.0") == ["F", "C", "R6.0", "A"]  # 3-bet to 3x
    assert tokens(tree(20.0), "R2.5") == ["F", "C", "R7.5", "A"]


def test_facing_a_three_bet_allows_only_an_all_in_four_bet() -> None:
    game = tree(20.0)
    node = game.node("R2.5-R7.5")  # BTN opens 2.5, SB 3-bets to 7.5: BB to act
    assert node.actor is Position.BB
    assert tokens(game, "R2.5-R7.5") == ["F", "C", "A"]
    assert node.raise_level == 2


def test_after_a_four_bet_all_in_only_fold_or_call() -> None:
    game = tree(20.0)
    node = game.node("R2.0-R6.0-A")  # BB 4-bets all-in, BTN to act
    assert node.actor is Position.BTN
    assert tokens(game, "R2.0-R6.0-A") == ["F", "C"]
    assert node.raise_level == 3


def test_a_caller_facing_a_squeeze_can_four_bet() -> None:
    # BTN opens, SB calls, BB 3-bets: BTN then SB face a 3-bet (D-005).
    game = tree(20.0)
    assert tokens(game, "R2.0-C-R6.0") == ["F", "C", "A"]
    assert tokens(game, "R2.0-C-R6.0-F") == ["F", "C", "A"]
    assert game.node("R2.0-C-R6.0-F").actor is Position.SB


def test_action_amounts_are_raise_to_totals() -> None:
    actions = tree(20.0).node("R2.0").actions
    assert [(a.token, a.amount) for a in actions] == [
        ("F", 0.5),
        ("C", 2.0),
        ("R6.0", 6.0),
        ("A", 20.0),
    ]


# --- Contributions, stacks and terminals ----------------------------------------------------


def test_root_holds_the_blinds() -> None:
    root = tree(12.0).root
    assert root.id == ROOT_ID
    assert root.actor is Position.BTN
    assert root.contributions == (0.0, 0.5, 1.0)
    assert root.stacks == (12.0, 11.5, 11.0)
    assert root.raise_level == 0


def test_btn_and_sb_fold_the_big_blind_wins_the_blinds() -> None:
    node = tree(12.0).node("F-F")
    assert node.terminal is TerminalKind.FOLD
    assert node.folded == (True, True, False)
    assert node.contributions == (0.0, 0.5, 1.0)
    assert node.pot == 1.5
    assert node.actions == ()
    assert node.actor is None


def test_heads_up_called_open_goes_to_the_flop() -> None:
    node = tree(12.0).node("R2.0-F-C")
    assert node.terminal is TerminalKind.FLOP
    assert node.contributions == (2.0, 0.5, 2.0)
    assert node.stacks == (10.0, 11.5, 10.0)
    assert node.pot == 4.5
    assert node.raise_level == 1


def test_three_way_all_in_is_a_showdown() -> None:
    node = tree(12.0).node("A-C-C")
    assert node.terminal is TerminalKind.SHOWDOWN
    assert node.contributions == (12.0, 12.0, 12.0)
    assert node.stacks == (0.0, 0.0, 0.0)


def test_called_three_bet_heads_up_goes_to_the_flop() -> None:
    node = tree(20.0).node("R2.5-R7.5-F-C")  # BB folds, BTN calls the 3-bet
    assert node.terminal is TerminalKind.FLOP
    assert node.contributions == (7.5, 7.5, 1.0)
    assert node.raise_level == 2


# --- Identifiers ----------------------------------------------------------------------------


def test_identifiers_are_stable_between_builds() -> None:
    assert list(tree(20.0).nodes) == list(tree(20.0).nodes)


def test_children_ids_extend_the_parent_path() -> None:
    game = tree(20.0)
    for node in game.nodes.values():
        assert len(node.children) == len(node.actions)
        for action, child in zip(node.actions, node.children, strict=True):
            expected = action.token if node.id == ROOT_ID else f"{node.id}-{action.token}"
            assert child == expected
            assert child in game.nodes


def test_unknown_node_is_an_error() -> None:
    with pytest.raises(KeyError):
        tree(12.0).node("R9.9")


# --- All-in conversion (D-011) ----------------------------------------------------------------


def test_raise_leaving_less_than_1bb_becomes_the_all_in() -> None:
    table = SizingTable(
        short=TrancheSizings(),
        medium=TrancheSizings(open_raises=(2.0, 8.5), isolation_base=3.0),
        deep=TrancheSizings(),
    )
    game = build_tree(GameConfig(stacks=(9.0, 9.0, 9.0), sizing_table=table))
    assert tokens(game, ROOT_ID) == ["F", "R2.0", "A"]  # 8.5 leaves 0.5: merged into A


# --- Invariants on the whole default grid ---------------------------------------------------


@pytest.mark.parametrize("config", default_configs(), ids=lambda c: f"{c.stacks[0]:g}bb")
def test_invariants_on_every_default_config(config: GameConfig) -> None:
    game = build_tree(config)
    for node in game.nodes.values():
        for i in range(3):
            assert node.contributions[i] + node.stacks[i] == pytest.approx(config.stacks[i])
            assert node.stacks[i] >= 0
        assert node.pot == pytest.approx(sum(node.contributions))
        live = [i for i in range(3) if not node.folded[i]]
        if node.terminal is None:
            assert node.actor is not None
            assert not node.folded[node.actor]
            assert node.stacks[node.actor] > 0
            assert node.actions
        else:
            assert node.actor is None
            assert node.actions == ()
            behind = [i for i in live if node.stacks[i] > 0]
            if node.terminal is TerminalKind.FOLD:
                assert len(live) == 1
            elif node.terminal is TerminalKind.SHOWDOWN:
                assert len(live) >= 2
                assert len(behind) <= 1
            else:  # FLOP
                assert len(behind) >= 2
                assert len({node.contributions[i] for i in live}) == 1
