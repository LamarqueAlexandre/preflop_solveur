"""Tests for the preflop action tree (FR-004, FR-005, D-005, D-011)."""

from collections import Counter

import pytest

from engine.game import (
    ROOT_ID,
    ActionKind,
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
    # Every raise is all-in. BTN: F / C / A.
    # F: SB F / C / A. F-C: BB X / A, then SB F / C. F-A: BB F / C.
    # C: SB F / C / A. C-F: BB X / A, then BTN F / C. C-C: BB X / A, then BTN and SB F / C.
    # C-A: BB then BTN F / C. A: SB then BB F / C.
    game = tree(5.0)
    assert counts(game) == (18, 22)
    assert terminal_kinds(game) == {
        TerminalKind.FOLD: 7,
        TerminalKind.SHOWDOWN: 12,
        TerminalKind.FLOP: 3,
    }
    assert set(game.nodes) == {
        ROOT_ID,
        "F",
        "F-F",
        "F-C",
        "F-C-X",
        "F-C-A",
        "F-C-A-F",
        "F-C-A-C",
        "F-A",
        "F-A-F",
        "F-A-C",
        "C",
        "C-F",
        "C-F-X",
        "C-F-A",
        "C-F-A-F",
        "C-F-A-C",
        "C-C",
        "C-C-X",
        "C-C-A",
        "C-C-A-F",
        "C-C-A-F-F",
        "C-C-A-F-C",
        "C-C-A-C",
        "C-C-A-C-F",
        "C-C-A-C-C",
        "C-A",
        "C-A-F",
        "C-A-F-F",
        "C-A-F-C",
        "C-A-C",
        "C-A-C-F",
        "C-A-C-C",
        "A",
        "A-F",
        "A-F-F",
        "A-F-C",
        "A-C",
        "A-C-F",
        "A-C-C",
    }


def test_medium_tree_counted_by_hand() -> None:
    # Raises-only part (#15): 18 decisions, 25 terminals, 4 flops.
    # SB complete (F-C): BB X / R3 / A -> 4 decisions, 7 terminals, 2 flops.
    # BTN limp (C): 32 decisions, 44 terminals, 9 flops.
    game = tree(12.0)
    assert counts(game) == (54, 76)
    assert terminal_kinds(game)[TerminalKind.FLOP] == 15


def test_deep_tree_counted_by_hand() -> None:
    # Raises-only part (#15): 78 decisions, 115 terminals, 24 flops.
    # SB complete (F-C): 6 decisions, 11 terminals, 3 flops.
    # BTN limp (C): 78 decisions, 112 terminals, 24 flops.
    game = tree(20.0)
    assert counts(game) == (162, 238)
    assert terminal_kinds(game)[TerminalKind.FLOP] == 51


@pytest.mark.parametrize(
    ("stack", "expected"),
    [
        (3.0, (18, 22)),
        (8.0, (18, 22)),
        (9.0, (54, 76)),
        (15.0, (54, 76)),
        (16.0, (162, 238)),
    ],
)
def test_tranche_bounds(stack: float, expected: tuple[int, int]) -> None:
    assert counts(tree(stack)) == expected


# --- Actions by situation (FR-004, D-005) ------------------------------------------------------


def test_open_actions_by_tranche() -> None:
    assert tokens(tree(5.0), ROOT_ID) == ["F", "C", "A"]
    assert tokens(tree(12.0), ROOT_ID) == ["F", "C", "R2.0", "A"]
    assert tokens(tree(20.0), ROOT_ID) == ["F", "C", "R2.0", "R2.5", "A"]


def test_sb_opens_when_btn_folds() -> None:
    game = tree(20.0)
    assert game.node("F").actor is Position.SB
    assert tokens(game, "F") == ["F", "C", "R2.0", "R2.5", "A"]


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


# --- Limps, completes and isolation raises (FR-004, FR-005, D-005, D-011) -------------------


@pytest.mark.parametrize("stack", [3.0, 8.0, 9.0, 15.0, 16.0, 25.0])
def test_btn_limp_and_sb_complete_at_every_depth(stack: float) -> None:
    game = tree(stack)
    limp = game.root.actions[1]
    assert (limp.kind, limp.amount) == (ActionKind.CALL, 1.0)
    complete = game.node("F").actions[1]
    assert (complete.kind, complete.amount) == (ActionKind.CALL, 1.0)
    assert game.node("F-C").contributions == (0.0, 1.0, 1.0)


def test_limp_is_not_a_raise() -> None:
    node = tree(20.0).node("C")
    assert node.actor is Position.SB
    assert node.raise_level == 0
    assert node.contributions == (1.0, 0.5, 1.0)


def test_facing_one_limp_by_tranche() -> None:
    assert tokens(tree(5.0), "C") == ["F", "C", "A"]  # isolation is all-in when short
    assert tokens(tree(12.0), "C") == ["F", "C", "R3.0", "A"]
    assert tokens(tree(20.0), "C") == ["F", "C", "R3.0", "A"]  # isolation replaces the opens


def test_big_blind_checks_and_never_folds_facing_limps() -> None:
    game = tree(20.0)
    assert tokens(game, "F-C") == ["X", "R3.0", "A"]  # SB completes: one limper
    assert tokens(game, "C-F") == ["X", "R3.0", "A"]  # BTN limps, SB folds
    assert tokens(game, "C-C") == ["X", "R4.0", "A"]  # two limpers: 3bb + 1bb
    check = game.node("C-C").actions[0]
    assert (check.kind, check.amount) == (ActionKind.CHECK, 1.0)


def test_big_blind_facing_limps_when_short() -> None:
    assert tokens(tree(5.0), "C-C") == ["X", "A"]
    assert tokens(tree(5.0), "F-C") == ["X", "A"]


def test_isolation_counts_the_sb_complete_as_a_limp() -> None:
    node = tree(12.0).node("C-C-R4.0")
    assert node.contributions == (1.0, 1.0, 4.0)
    assert node.raise_level == 1
    assert node.actor is Position.BTN


def test_facing_an_isolation_raise_uses_the_facing_a_raise_actions() -> None:
    game = tree(20.0)
    assert tokens(game, "C-R3.0") == ["F", "C", "R9.0", "A"]  # BB facing SB's isolation
    assert tokens(game, "C-C-R4.0") == ["F", "C", "R12.0", "A"]
    assert tokens(tree(12.0), "C-R3.0") == ["F", "C", "A"]


def test_isolated_limper_can_reraise() -> None:
    # D-005: BTN limps, SB isolates, BB folds, BTN limp-reraises.
    game = tree(20.0)
    assert game.node("C-R3.0-F").actor is Position.BTN
    assert tokens(game, "C-R3.0-F") == ["F", "C", "R9.0", "A"]
    assert tokens(game, "C-R3.0-F-R9.0") == ["F", "C", "A"]  # SB faces it: 4-bet all-in only
    assert tokens(game, "C-R3.0-F-R9.0-A") == ["F", "C"]


def test_isolation_leaving_less_than_1bb_becomes_the_all_in() -> None:
    table = SizingTable(
        short=TrancheSizings(),
        medium=TrancheSizings(open_raises=(2.0,), isolation_base=7.5),
        deep=TrancheSizings(),
    )
    game = build_tree(GameConfig(stacks=(9.0, 9.0, 9.0), sizing_table=table))
    assert tokens(game, "F-C") == ["X", "R7.5", "A"]  # one limper: 7.5 leaves 1.5
    assert tokens(game, "C-C") == ["X", "A"]  # two limpers: 8.5 leaves 0.5, merged into A


@pytest.mark.parametrize(
    ("node_id", "live", "pot"),
    [
        ("F-C-X", (False, True, True), 2.0),  # SB completes, BB checks
        ("C-F-X", (True, False, True), 2.5),  # the SB's folded blind stays in the pot
        ("C-C-X", (True, True, True), 3.0),
    ],
)
@pytest.mark.parametrize("stack", [5.0, 12.0, 20.0])
def test_limped_pots_go_to_the_flop(
    stack: float, node_id: str, live: tuple[bool, bool, bool], pot: float
) -> None:
    node = tree(stack).node(node_id)
    assert node.terminal is TerminalKind.FLOP
    assert node.raise_level == 0
    assert tuple(not folded for folded in node.folded) == live
    assert node.pot == pot


@pytest.mark.parametrize("stack", [5.0, 12.0, 20.0])
def test_only_three_limped_pots(stack: float) -> None:
    game = tree(stack)
    limped = {
        node.id
        for node in game.nodes.values()
        if node.terminal is TerminalKind.FLOP and node.raise_level == 0
    }
    assert limped == {"F-C-X", "C-F-X", "C-C-X"}


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
    assert tokens(game, ROOT_ID) == ["F", "C", "R2.0", "A"]  # 8.5 leaves 0.5: merged into A


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
            kinds = [action.kind for action in node.actions]
            unraised_bb = node.actor is Position.BB and node.raise_level == 0
            assert (ActionKind.CHECK in kinds) == unraised_bb
            assert (ActionKind.FOLD in kinds) != unraised_bb
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
