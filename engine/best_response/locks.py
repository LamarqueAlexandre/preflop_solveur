"""Villain locks: fixed strategies at some nodes of a solution (FR-014, FR-015)."""

from collections.abc import Mapping

import numpy as np

from engine.game.tree import GameTree, Position
from engine.solver import Strategy

Locks = Mapping[str, Strategy]
"""``{node_id: strategy (actions, classes)}`` at villain decision nodes."""

_SUM_TOLERANCE = 1e-9


def validate_locks(
    tree: GameTree, locks: Locks, hero: Position, n_classes: int
) -> dict[str, Strategy]:
    """Check every lock and return them as float arrays; ``ValueError`` otherwise.

    A lock must be on a decision node of a villain (not the hero) and be a
    probability distribution over the node's actions for each hand class.
    """
    checked: dict[str, Strategy] = {}
    for node_id, raw in locks.items():
        if node_id not in tree.nodes:
            raise ValueError(f"cannot lock unknown node {node_id!r}")
        node = tree.node(node_id)
        if node.actor is None:
            raise ValueError(f"cannot lock terminal node {node_id!r}")
        if node.actor is hero:
            raise ValueError(
                f"node {node_id!r} belongs to the hero ({hero.name}): it cannot be locked"
            )
        strategy = np.asarray(raw, dtype=np.float64)
        expected = (len(node.actions), n_classes)
        if strategy.shape != expected:
            raise ValueError(
                f"lock of {node_id!r} must have shape {expected}, got {strategy.shape}"
            )
        if (strategy < 0).any() or not np.allclose(
            strategy.sum(axis=0), 1.0, rtol=0, atol=_SUM_TOLERANCE
        ):
            raise ValueError(f"lock of {node_id!r} is not a probability distribution")
        checked[node_id] = strategy
    return checked
