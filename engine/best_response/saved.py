"""Saved villain strategies: one node's strategy, reusable on other spots (FR-017, D-020).

A saved strategy lists its actions by label (``"F"``, ``"C"``, ``"R2.0"``,
``"A"``) and gives their frequencies for the 169 hand classes. It applies to
any decision node whose actions have exactly the same labels, in any order;
anywhere else it is refused rather than mapped by guesswork.
"""

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike

from engine.best_response.locks import check_strategy
from engine.cards import N_CLASSES
from engine.game.tree import GameTree
from engine.solver import Strategy


def validate_saved(actions: Sequence[str], frequencies: ArrayLike) -> Strategy:
    """Check a saved strategy: distinct non-empty labels, (actions, 169) distribution."""
    if not actions:
        raise ValueError("a saved strategy needs at least one action")
    if any(not label for label in actions):
        raise ValueError("action labels cannot be empty")
    if len(set(actions)) != len(actions):
        raise ValueError(f"action labels must be distinct, got {list(actions)}")
    return check_strategy(frequencies, len(actions), N_CLASSES)


def lock_from_saved(
    tree: GameTree, node_id: str, actions: Sequence[str], frequencies: ArrayLike
) -> Strategy:
    """Lock of ``node_id`` from a saved strategy, rows in the node's action order.

    ``ValueError`` if the node is unknown or terminal, or if its actions are
    not exactly the saved ones (the message lists both).
    """
    strategy = validate_saved(actions, frequencies)
    if node_id not in tree.nodes:
        raise ValueError(f"unknown node {node_id!r}")
    node = tree.node(node_id)
    if node.actor is None:
        raise ValueError(f"node {node_id!r} is terminal: it has no strategy")
    node_actions = [action.token for action in node.actions]
    if set(node_actions) != set(actions):
        raise ValueError(
            f"the saved strategy plays {', '.join(actions)} but node {node_id!r} offers "
            f"{', '.join(node_actions)}: it only applies to nodes with the same actions"
        )
    row = {label: k for k, label in enumerate(actions)}
    return np.ascontiguousarray(strategy[[row[label] for label in node_actions]])
