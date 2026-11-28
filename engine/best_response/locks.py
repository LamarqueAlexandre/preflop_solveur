"""Villain locks: fixed strategies at some nodes of a solution (FR-014, FR-015)."""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike

from engine.cards import N_CLASSES, format_class
from engine.game.tree import GameTree, Position
from engine.solver import Strategy

Locks = Mapping[str, Strategy]
"""``{node_id: strategy (actions, classes)}`` at villain decision nodes."""

_SUM_TOLERANCE = 1e-9
_MAX_LISTED_HANDS = 12


class StrategyError(ValueError):
    """Invalid strategy; ``hands`` names the hand classes at fault, if any."""

    def __init__(self, message: str, hands: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.hands = hands


def check_strategy(
    raw: ArrayLike, n_actions: int, n_classes: int = N_CLASSES, label: str = "strategy"
) -> Strategy:
    """``raw`` as a float array of shape (n_actions, n_classes); ``StrategyError`` otherwise.

    Each hand class must get a probability distribution over the actions:
    finite, non-negative frequencies summing to 1 (spec edge case: the hands at
    fault are reported).
    """
    expected = (n_actions, n_classes)
    try:
        strategy = np.asarray(raw, dtype=np.float64)
    except ValueError:
        raise StrategyError(f"{label} must have shape {expected}: ragged rows") from None
    if strategy.shape != expected:
        raise StrategyError(f"{label} must have shape {expected}, got {strategy.shape}")
    with np.errstate(invalid="ignore"):
        faulty = (
            ~np.isfinite(strategy).all(axis=0)
            | (strategy < 0).any(axis=0)
            | ~np.isclose(strategy.sum(axis=0), 1.0, rtol=0, atol=_SUM_TOLERANCE)
        )
    if faulty.any():
        hands = tuple(format_class(int(h)) for h in np.flatnonzero(faulty))
        listed = ", ".join(hands[:_MAX_LISTED_HANDS])
        more = (
            f" and {len(hands) - _MAX_LISTED_HANDS} more" if len(hands) > _MAX_LISTED_HANDS else ""
        )
        raise StrategyError(
            f"{label} is not a probability distribution for hands {listed}{more}", hands
        )
    return strategy


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
        checked[node_id] = check_strategy(
            raw, len(node.actions), n_classes, label=f"lock of {node_id!r}"
        )
    return checked
