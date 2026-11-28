"""Tests for the per-node reaches and conditional EVs (FR-011, US2 scenario 3).

Reference game (same as test_exploitability.py, solved in docs/notes/cfr.md):
heads-up push/fold between SB and BB, the BTN has folded; two classes, STRONG
has 75% against WEAK; W = 1 (no card removal). The EVs below are computed by
hand in docs/notes/solution-ev.md.
"""

from types import MappingProxyType

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
from engine.realization import default_profile
from engine.solver import EquityTables, TerminalValues, exploitability, node_values

STRONG, WEAK = 0, 1
BTN, SB, BB = int(Position.BTN), int(Position.SB), int(Position.BB)


def strength_tables(strengths: list[float], w: np.ndarray | None = None) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    weights = np.ones((n, n, n)) if w is None else w
    return EquityTables.from_arrays(weights, e3, e2)


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


def push_fold_game(stack: float) -> tuple[GameTree, TerminalValues]:
    tree = push_fold_tree(stack)
    return tree, TerminalValues(tree, strength_tables([3.0, 1.0]), default_profile())


def strategy(strong: list[float], weak: list[float]) -> np.ndarray:
    """(actions, classes) array from the action probabilities of each class."""
    return np.array([strong, weak]).T


EQUILIBRIUM_10BB = {
    ROOT_ID: strategy([0.0, 1.0], [1.0, 0.0]),
    "A": strategy([0.0, 1.0], [1.0, 0.0]),
}
"""S = 10: STRONG pushes and calls, WEAK folds on both sides."""


# --- Reference game, computed by hand ----------------------------------------------------


def test_action_evs_at_the_root_are_conditional_on_the_hand() -> None:
    """SB WEAK pushing: -5 against a calling STRONG, +1 against a folding WEAK, so -2."""
    tree, values = push_fold_game(10.0)
    result = node_values(tree, values, EQUILIBRIUM_10BB)
    np.testing.assert_allclose(result.ev_at("F")[SB], [-0.5, -0.5])
    np.testing.assert_allclose(result.ev_at("A")[SB], [0.5, -2.0])
    np.testing.assert_allclose(result.ev_at(ROOT_ID)[SB], [0.5, -0.5])


def test_action_evs_facing_the_push_see_only_the_pushing_range() -> None:
    """Only STRONG reaches the push: BB WEAK calling gets 0.25 * 20 - 10 = -5."""
    tree, values = push_fold_game(10.0)
    result = node_values(tree, values, EQUILIBRIUM_10BB)
    np.testing.assert_allclose(result.ev_at("A-F")[BB], [-1.0, -1.0])
    np.testing.assert_allclose(result.ev_at("A-C")[BB], [0.0, -5.0])
    np.testing.assert_allclose(result.ev_at("A")[BB], [0.0, -1.0])


def test_non_actor_ev_weights_the_children_by_the_actor_range() -> None:
    """BB at the root: STRONG 0.5 * 0 + 0.5 * 0.5 = 0.25, WEAK 0.5 * -1 + 0.5 * 0.5 = -0.25."""
    tree, values = push_fold_game(10.0)
    result = node_values(tree, values, EQUILIBRIUM_10BB)
    np.testing.assert_allclose(result.ev_at(ROOT_ID)[BB], [0.25, -0.25])
    np.testing.assert_allclose(result.ev_at(ROOT_ID)[BTN], [0.0, 0.0])


def test_reaches_are_the_products_of_the_own_action_probabilities() -> None:
    tree, values = push_fold_game(10.0)
    profile = {
        ROOT_ID: strategy([0.0, 1.0], [0.75, 0.25]),
        "A": strategy([0.2, 0.8], [0.9, 0.1]),
    }
    result = node_values(tree, values, profile)
    np.testing.assert_allclose(result.reach_at(ROOT_ID), np.ones((3, 2)))
    np.testing.assert_allclose(result.reach_at("A"), [[1.0, 1.0], [1.0, 0.25], [1.0, 1.0]])
    np.testing.assert_allclose(result.reach_at("A-C"), [[1.0, 1.0], [1.0, 0.25], [0.8, 0.1]])
    np.testing.assert_allclose(result.reach_at("F"), [[1.0, 1.0], [0.0, 0.75], [1.0, 1.0]])


def test_ev_is_undefined_where_the_opponents_never_arrive() -> None:
    """The SB never pushes: the BB's (and BTN's) EV after a push has no meaning."""
    tree, values = push_fold_game(10.0)
    profile = {
        ROOT_ID: strategy([1.0, 0.0], [1.0, 0.0]),
        "A": strategy([0.0, 1.0], [1.0, 0.0]),
    }
    result = node_values(tree, values, profile)
    for node_id in ("A", "A-F", "A-C"):
        assert np.isnan(result.ev_at(node_id)[BB]).all()
        assert np.isnan(result.ev_at(node_id)[BTN]).all()
        assert not np.isnan(result.ev_at(node_id)[SB]).any()
    np.testing.assert_allclose(result.opponent_mass_at("A")[BB], [0.0, 0.0])
    np.testing.assert_allclose(result.ev_at("A")[SB], [0.5, -2.0])


def test_node_ids_follow_the_tree_and_unknown_nodes_are_rejected() -> None:
    tree, values = push_fold_game(10.0)
    result = node_values(tree, values, EQUILIBRIUM_10BB)
    assert result.node_ids == tuple(node.id for node in tree)
    assert result.ev.shape == result.reach.shape == (len(tree), 3, 2)
    with pytest.raises(KeyError):
        result.ev_at("nope")


def test_arrays_are_read_only() -> None:
    tree, values = push_fold_game(10.0)
    result = node_values(tree, values, EQUILIBRIUM_10BB)
    for array in (result.ev, result.reach, result.opponent_mass):
        with pytest.raises(ValueError):
            array[0, 0, 0] = 1.0


def test_an_invalid_profile_is_rejected() -> None:
    tree, values = push_fold_game(10.0)
    with pytest.raises(ValueError, match="no strategy"):
        node_values(tree, values, {ROOT_ID: EQUILIBRIUM_10BB[ROOT_ID]})


# --- Properties on three-max trees -------------------------------------------------------


def random_profile(tree: GameTree, n: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    profile = {}
    for node in tree:
        if not node.is_terminal:
            raw = rng.random((len(node.actions), n))
            profile[node.id] = raw / raw.sum(axis=0)
    return profile


def removal_weights(n: int, rng: np.random.Generator) -> np.ndarray:
    """Symmetric W with some impossible triplets (card removal), every class possible."""
    raw = rng.integers(0, 4, size=(n, n, n)).astype(np.float64)
    w = sum(
        raw.transpose(p) for p in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
    )
    w[w < 6] = 0.0
    w[np.arange(n), np.arange(n), np.arange(n)] = 0.0
    assert (w.sum(axis=(1, 2)) > 0).all()
    return w


def three_max_game(
    stack: float, seed: int
) -> tuple[GameTree, TerminalValues, dict[str, np.ndarray], EquityTables]:
    rng = np.random.default_rng(seed)
    n = 4
    tree = build_tree(GameConfig.equal_stacks(stack))
    tables = strength_tables(list(rng.uniform(0.5, 3.0, n)), removal_weights(n, rng))
    values = TerminalValues(tree, tables, default_profile())
    return tree, values, random_profile(tree, n, rng), tables


STACKS = [5.0, 12.0, 20.0]


@pytest.mark.parametrize("stack", STACKS)
def test_actor_ev_is_the_strategy_weighted_ev_of_its_actions(stack: float) -> None:
    tree, values, profile, _ = three_max_game(stack, int(stack))
    result = node_values(tree, values, profile)
    for node in tree:
        if node.is_terminal:
            continue
        actor = int(node.actor)  # type: ignore[arg-type]
        children = np.array([result.ev_at(child)[actor] for child in node.children])
        expected = (profile[node.id] * children).sum(axis=0)
        np.testing.assert_allclose(result.ev_at(node.id)[actor], expected, atol=1e-9)


@pytest.mark.parametrize("stack", STACKS)
def test_non_actor_ev_weights_the_children_by_bayes(stack: float) -> None:
    """EV_p(n, h) = sum_a m_p(child_a, h) / m_p(n, h) * EV_p(child_a, h)."""
    tree, values, profile, _ = three_max_game(stack, 10 + int(stack))
    result = node_values(tree, values, profile)
    for node in tree:
        if node.is_terminal:
            continue
        for player in range(3):
            if player == int(node.actor):  # type: ignore[arg-type]
                continue
            mass = result.opponent_mass_at(node.id)[player]
            weighted = sum(
                result.opponent_mass_at(child)[player] * result.ev_at(child)[player]
                for child in node.children
            )
            np.testing.assert_allclose(mass * result.ev_at(node.id)[player], weighted, atol=1e-9)


@pytest.mark.parametrize("stack", STACKS)
def test_opponent_mass_counts_the_compatible_opponent_hands(stack: float) -> None:
    tree, values, profile, tables = three_max_game(stack, 20 + int(stack))
    result = node_values(tree, values, profile)
    for node_id in result.node_ids[:: max(1, len(result.node_ids) // 15)]:
        r = result.reach_at(node_id)
        expected = (
            np.einsum("hxy,x,y->h", tables.w, r[SB], r[BB]),
            np.einsum("xhy,x,y->h", tables.w, r[BTN], r[BB]),
            np.einsum("xyh,x,y->h", tables.w, r[BTN], r[SB]),
        )
        np.testing.assert_allclose(result.opponent_mass_at(node_id), expected, atol=1e-9)


@pytest.mark.parametrize("stack", STACKS)
def test_root_evs_match_the_exploitability_evs_and_sum_to_zero(stack: float) -> None:
    tree, values, profile, _ = three_max_game(stack, 30 + int(stack))
    result = node_values(tree, values, profile)
    mass = values.hand_mass()
    root_ev = [float(mass @ result.ev_at(ROOT_ID)[p]) / float(mass.sum()) for p in range(3)]
    assert root_ev == pytest.approx(list(exploitability(tree, values, profile).ev), abs=1e-9)
    assert sum(root_ev) == pytest.approx(0.0, abs=1e-9)
