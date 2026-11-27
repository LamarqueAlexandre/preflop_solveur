"""Vectorized tree traversal shared by DCFR and the best response.

Nodes are numbered in depth-first order (parents before children). A
traversal goes down to compute every player's reach under a strategy
profile, evaluates the terminals for one player, then goes back up.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from engine.game.tree import N_PLAYERS, ROOT_ID, GameTree, Position
from engine.solver.terminal import TerminalValues

Strategy = NDArray[np.float64]
"""Shape (n_actions, n_classes): probability of each action for each hand class."""

_SUM_TOLERANCE = 1e-9


class TreeIndex:
    """Integer view of a game tree: children, actors, decision and terminal nodes."""

    def __init__(self, tree: GameTree) -> None:
        nodes = list(tree)
        self.tree = tree
        self.ids = [node.id for node in nodes]
        self.index = {node_id: k for k, node_id in enumerate(self.ids)}
        if self.index.get(ROOT_ID) != 0:
            raise ValueError("the root must be the first node of the tree")
        self.children = [[self.index[child] for child in node.children] for node in nodes]
        if any(child <= k for k, children in enumerate(self.children) for child in children):
            raise ValueError("tree nodes must be in depth-first order (parents first)")
        self.actors = [None if node.actor is None else int(node.actor) for node in nodes]
        self.n_actions = [len(node.actions) for node in nodes]
        self.decisions = [k for k, node in enumerate(nodes) if not node.is_terminal]
        self.terminals = [k for k, node in enumerate(nodes) if node.is_terminal]

    def __len__(self) -> int:
        return len(self.ids)

    def check_profile(self, profile: Mapping[str, Strategy], n_classes: int) -> dict[int, Strategy]:
        """Validate a strategy for every decision node; key them by node index."""
        checked: dict[int, Strategy] = {}
        for k in self.decisions:
            node_id = self.ids[k]
            if node_id not in profile:
                raise ValueError(f"no strategy for decision node {node_id!r}")
            strategy = np.asarray(profile[node_id], dtype=np.float64)
            if strategy.shape != (self.n_actions[k], n_classes):
                raise ValueError(
                    f"strategy of {node_id!r} must have shape "
                    f"({self.n_actions[k]}, {n_classes}), got {strategy.shape}"
                )
            if (strategy < 0).any() or not np.allclose(
                strategy.sum(axis=0), 1.0, rtol=0, atol=_SUM_TOLERANCE
            ):
                raise ValueError(f"strategy of {node_id!r} is not a probability distribution")
            checked[k] = strategy
        return checked

    def reaches(self, strategies: Mapping[int, Strategy], n_classes: int) -> NDArray[np.float64]:
        """Reach of each player at each node, shape (nodes, players, classes)."""
        reaches = np.empty((len(self), N_PLAYERS, n_classes))
        reaches[0] = 1.0
        for k in self.decisions:
            actor = self.actors[k]
            assert actor is not None
            for a, child in enumerate(self.children[k]):
                reaches[child] = reaches[k]
                reaches[child, actor] *= strategies[k][a]
        return reaches

    def terminal_values(
        self, values: TerminalValues, player: int, reaches: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Array (nodes, classes) holding the player's values at the terminals."""
        result = np.zeros((len(self), values.n_classes))
        batch = values.values_batch(
            Position(player), {self.ids[k]: tuple(reaches[k]) for k in self.terminals}
        )
        for k in self.terminals:
            result[k] = batch[self.ids[k]]
        return result
