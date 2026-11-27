"""Discounted CFR, vectorized over hand classes (FR-009, D-014).

Brown & Sandholm (2019), *Solving Imperfect-Information Games via Discounted
Regret Minimization*. Each iteration updates the players one after the other
(BTN, SB, BB: alternating updates). For the updated player:

1. top-down: reach of each player at each node, for every hand class, under
   the current strategies (regret matching of the cumulative regrets);
2. terminal values of the player (``TerminalValues.values_batch``);
3. bottom-up: node values, then the player's regrets
   ``R(a) += v(a) - sum_b sigma(b) v(b)`` and strategy sum ``+= reach * sigma``;
4. discount at the end of iteration t: positive regrets by t^a / (t^a + 1),
   negative regrets by t^b / (t^b + 1), strategy sum by (t / (t + 1))^g.

No convergence guarantee exists with three players: the exploitability
(NashConv, #20) is the equilibrium certificate.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from engine.game.tree import N_PLAYERS, ROOT_ID, GameTree, Position
from engine.solver.terminal import TerminalValues

Strategy = NDArray[np.float64]
"""Shape (n_actions, n_classes): probability of each action for each hand class."""


@dataclass(frozen=True)
class DCFRParams:
    """Discount parameters; the defaults are those recommended by the paper (D-014)."""

    alpha: float = 1.5
    beta: float = 0.0
    gamma: float = 2.0

    def positive_discount(self, t: int) -> float:
        """Factor applied to positive cumulative regrets at the end of iteration t."""
        power: float = float(t) ** self.alpha
        return power / (power + 1.0)

    def negative_discount(self, t: int) -> float:
        """Factor applied to negative cumulative regrets at the end of iteration t."""
        power: float = float(t) ** self.beta
        return power / (power + 1.0)

    def strategy_discount(self, t: int) -> float:
        """Factor applied to the strategy sum at the end of iteration t."""
        return float((t / (t + 1.0)) ** self.gamma)


def regret_matching(regrets: NDArray[np.float64]) -> Strategy:
    """Play each action in proportion to its positive regret; uniform if none is positive."""
    positive = np.maximum(regrets, 0.0)
    total = positive.sum(axis=0)
    has_positive = total > 0
    uniform = 1.0 / regrets.shape[0]
    return np.where(has_positive, positive / np.where(has_positive, total, 1.0), uniform)


def _normalize(strategy_sum: NDArray[np.float64]) -> Strategy:
    total = strategy_sum.sum(axis=0)
    reached = total > 0
    uniform = 1.0 / strategy_sum.shape[0]
    return np.where(reached, strategy_sum / np.where(reached, total, 1.0), uniform)


class DCFRSolver:
    """Discounted CFR on any game tree, vectorized over the hand classes."""

    def __init__(
        self,
        tree: GameTree,
        terminal_values: TerminalValues,
        params: DCFRParams | None = None,
    ) -> None:
        self._tree = tree
        self._values = terminal_values
        self._params = params or DCFRParams()
        nodes = list(tree)
        self._ids = [node.id for node in nodes]
        index = {node_id: k for k, node_id in enumerate(self._ids)}
        if index.get(ROOT_ID) != 0:
            raise ValueError("the root must be the first node of the tree")
        self._children = [[index[child] for child in node.children] for node in nodes]
        if any(child <= k for k, children in enumerate(self._children) for child in children):
            raise ValueError("tree nodes must be in depth-first order (parents first)")
        self._actors = [None if node.actor is None else int(node.actor) for node in nodes]
        self._decisions = [k for k, node in enumerate(nodes) if not node.is_terminal]
        self._terminals = [k for k, node in enumerate(nodes) if node.is_terminal]

        n = terminal_values.n_classes
        self._regrets = {k: np.zeros((len(nodes[k].actions), n)) for k in self._decisions}
        self._strategy_sum = {k: np.zeros((len(nodes[k].actions), n)) for k in self._decisions}
        self._iterations = 0

    @property
    def tree(self) -> GameTree:
        return self._tree

    @property
    def params(self) -> DCFRParams:
        return self._params

    @property
    def iterations(self) -> int:
        return self._iterations

    def regrets(self, node_id: str) -> NDArray[np.float64]:
        """Cumulative (discounted) regrets of a decision node, shape (actions, classes)."""
        return self._regrets[self._ids.index(node_id)].copy()

    def current_strategy(self) -> dict[str, Strategy]:
        """Regret-matching strategy of every decision node."""
        return {self._ids[k]: regret_matching(self._regrets[k]) for k in self._decisions}

    def average_strategy(self) -> dict[str, Strategy]:
        """Average strategy of every decision node (uniform for hands never reaching it)."""
        return {self._ids[k]: _normalize(self._strategy_sum[k]) for k in self._decisions}

    def iterate(self, n: int = 1) -> None:
        """Run ``n`` iterations, each updating BTN, SB then BB."""
        for _ in range(n):
            t = self._iterations + 1
            for player in Position:
                self._update(int(player), t)
            self._iterations = t

    def _update(self, player: int, t: int) -> None:
        strategies = {k: regret_matching(self._regrets[k]) for k in self._decisions}
        n_nodes, n = len(self._ids), self._values.n_classes

        reaches = np.empty((n_nodes, N_PLAYERS, n))
        reaches[0] = 1.0
        for k in self._decisions:
            actor = self._actors[k]
            assert actor is not None
            for a, child in enumerate(self._children[k]):
                reaches[child] = reaches[k]
                reaches[child, actor] *= strategies[k][a]

        values = np.empty((n_nodes, n))
        terminal_values = self._values.values_batch(
            Position(player), {self._ids[k]: tuple(reaches[k]) for k in self._terminals}
        )
        for k in self._terminals:
            values[k] = terminal_values[self._ids[k]]

        for k in reversed(self._decisions):
            child_values = values[self._children[k]]
            if self._actors[k] == player:
                strategy = strategies[k]
                values[k] = (strategy * child_values).sum(axis=0)
                self._regrets[k] += child_values - values[k]
                self._strategy_sum[k] += reaches[k, player] * strategy
            else:
                values[k] = child_values.sum(axis=0)

        params = self._params
        positive, negative = params.positive_discount(t), params.negative_discount(t)
        discount = params.strategy_discount(t)
        for k in self._decisions:
            if self._actors[k] == player:
                regrets = self._regrets[k]
                regrets *= np.where(regrets > 0, positive, negative)
                self._strategy_sum[k] *= discount
