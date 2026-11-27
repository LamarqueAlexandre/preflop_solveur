"""Tests for Discounted CFR (FR-009, D-014) and the batched terminal values.

The reference game is a heads-up push/fold between SB and BB (the BTN has
already folded), with two hand classes: STRONG and WEAK. STRONG has 75% against
WEAK, identical classes split. Solved by hand (docs/notes/cfr.md): the SB
pushes WEAK with p = S/2 - 1, the BB calls with WEAK with q = 2 - S/2, STRONG
always pushes and calls. At S = 3, p = q = 0.5; at S = 10 the equilibrium is
pure (WEAK folds on both sides).
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
from engine.solver import DCFRParams, DCFRSolver, EquityTables, TerminalValues, regret_matching

STRONG, WEAK = 0, 1


def strength_tables(strengths: list[float], w: np.ndarray | None = None) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)) if w is None else w, e3, e2)


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
        config=GameConfig.equal_stacks(stack),
        nodes=MappingProxyType({n.id: n for n in nodes}),
    )


def push_fold_solver(stack: float, params: DCFRParams | None = None) -> DCFRSolver:
    tree = push_fold_tree(stack)
    values = TerminalValues(tree, strength_tables([3.0, 1.0]), default_profile())
    return DCFRSolver(tree, values, params or DCFRParams())


# --- Regret matching ---------------------------------------------------------------------


def test_regret_matching_is_proportional_to_positive_regrets() -> None:
    regrets = np.array([[3.0, 0.0], [-1.0, 2.0], [1.0, 2.0]])
    np.testing.assert_allclose(regret_matching(regrets), [[0.75, 0.0], [0.0, 0.5], [0.25, 0.5]])


def test_regret_matching_is_uniform_without_positive_regret() -> None:
    regrets = np.array([[-1.0, 0.0], [-2.0, 0.0]])
    np.testing.assert_allclose(regret_matching(regrets), [[0.5, 0.5], [0.5, 0.5]])


# --- Discount ----------------------------------------------------------------------------


def test_default_parameters_are_those_of_the_paper() -> None:
    params = DCFRParams()
    assert (params.alpha, params.beta, params.gamma) == (1.5, 0.0, 2.0)


def test_discount_factors() -> None:
    params = DCFRParams(alpha=1.5, beta=0.0, gamma=2.0)
    assert params.positive_discount(4) == pytest.approx(8 / 9)  # 4^1.5 = 8
    assert params.negative_discount(4) == pytest.approx(0.5)  # 4^0 = 1
    assert params.strategy_discount(4) == pytest.approx((4 / 5) ** 2)


# --- First iteration, computed by hand ---------------------------------------------------


def test_first_iteration_regrets() -> None:
    """Uniform first strategies; regrets are then discounted by 1/2 (t = 1).

    SB (updated first, BB uniform), per hand, summed over BTN's 2 dead classes:
    - WEAK: fold -2, push 2 * (0.5 * (-1.5) + 0.5 * 1 + 0.5 * 0 + 0.5 * 1) = 0.5,
      node -0.75, regrets -1.25 / +1.25;
    - STRONG: fold -2, push 2 * (0.5 * 0 + 0.5 + 0.5 * 1.5 + 0.5) = 3.5,
      node 0.75, regrets -2.75 / +2.75.
    BB (updated second, SB now pushes both hands):
    - STRONG: fold -4, call 2 * (0 + 1.5) = 3, node -0.5, regrets -3.5 / +3.5;
    - WEAK: fold -4, call 2 * (-1.5 + 0) = -3, node -3.5, regrets -0.5 / +0.5.
    """
    solver = push_fold_solver(3.0)
    solver.iterate(1)
    np.testing.assert_allclose(
        solver.regrets(ROOT_ID), 0.5 * np.array([[-2.75, -1.25], [2.75, 1.25]])
    )
    np.testing.assert_allclose(solver.regrets("A"), 0.5 * np.array([[-3.5, -0.5], [3.5, 0.5]]))
    np.testing.assert_allclose(solver.average_strategy()[ROOT_ID], 0.5)
    np.testing.assert_allclose(solver.current_strategy()[ROOT_ID], [[0.0, 0.0], [1.0, 1.0]])
    assert solver.iterations == 1


# --- Convergence -------------------------------------------------------------------------


def test_converges_to_the_mixed_equilibrium() -> None:
    solver = push_fold_solver(3.0)
    solver.iterate(3000)
    average = solver.average_strategy()
    push, call = average[ROOT_ID][1], average["A"][1]
    assert push[STRONG] == pytest.approx(1.0, abs=0.01)
    assert call[STRONG] == pytest.approx(1.0, abs=0.01)
    assert push[WEAK] == pytest.approx(0.5, abs=0.01)
    assert call[WEAK] == pytest.approx(0.5, abs=0.01)


def test_converges_to_the_pure_equilibrium() -> None:
    solver = push_fold_solver(10.0)
    solver.iterate(1000)
    average = solver.average_strategy()
    np.testing.assert_allclose(average[ROOT_ID][1], [1.0, 0.0], atol=0.01)
    np.testing.assert_allclose(average["A"][1], [1.0, 0.0], atol=0.01)


# --- Three-max tree ----------------------------------------------------------------------


def three_max_solver(stack: float) -> DCFRSolver:
    rng = np.random.default_rng(19)
    tables = strength_tables(list(rng.uniform(0.5, 3.0, 4)))
    tree = build_tree(GameConfig.equal_stacks(stack))
    return DCFRSolver(tree, TerminalValues(tree, tables, default_profile()))


@pytest.mark.parametrize("stack", [5.0, 12.0, 20.0])
def test_strategies_on_a_three_max_tree_are_distributions(stack: float) -> None:
    solver = three_max_solver(stack)
    solver.iterate(20)
    for strategies in (solver.average_strategy(), solver.current_strategy()):
        assert set(strategies) == {node.id for node in solver.tree if not node.is_terminal}
        for node_id, strategy in strategies.items():
            n_actions = len(solver.tree.node(node_id).actions)
            assert strategy.shape == (n_actions, 4)
            assert np.isfinite(strategy).all() and (strategy >= 0).all()
            np.testing.assert_allclose(strategy.sum(axis=0), 1.0)


def test_solver_is_deterministic() -> None:
    first, second = three_max_solver(12.0), three_max_solver(12.0)
    first.iterate(10)
    second.iterate(10)
    for node_id, strategy in first.average_strategy().items():
        np.testing.assert_array_equal(strategy, second.average_strategy()[node_id])


# --- Batched terminal values -------------------------------------------------------------


@pytest.mark.parametrize("stack", [3.0, 8.0, 12.0, 20.0, 25.0])
def test_values_batch_matches_values(stack: float) -> None:
    rng = np.random.default_rng(int(stack) + 100)
    n = 4
    raw = rng.integers(0, 4, size=(n, n, n)).astype(np.float64)
    perms = [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]
    w = sum(raw.transpose(p) for p in perms)
    tree = build_tree(GameConfig.equal_stacks(stack))
    values = TerminalValues(
        tree, strength_tables(list(rng.uniform(0.5, 3.0, n)), w), default_profile()
    )
    terminals = [node.id for node in tree if node.is_terminal]
    reaches = {node_id: tuple(rng.random(n) for _ in range(3)) for node_id in terminals}
    for player in Position:
        batch = values.values_batch(player, reaches)
        assert set(batch) == set(terminals)
        for node_id in terminals:
            np.testing.assert_allclose(
                batch[node_id],
                values.values(node_id, player, reaches[node_id]),
                rtol=1e-12,
                atol=1e-12,
            )
