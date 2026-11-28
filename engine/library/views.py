"""What the interface shows of a solution: node summary, terminal view, nearest depth.

Weights follow D-017: a hand class h of the actor counts for
``reach(h) · opponent_mass(h)``, its real frequency at the node in the
equilibrium game (card removal included). See docs/notes/vues-noeud.md.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from engine.cards import N_COMBOS
from engine.game.tree import N_PLAYERS, Position, TerminalKind
from engine.library.solution import Solution
from engine.library.store import SolutionSummary

Triple = tuple[float, float, float]


@dataclass(frozen=True)
class NodeSummary:
    """Range-wide view of a decision node (FR-021).

    ``frequencies[k]``: share of the actor's hands taking ``actions[k]``, None
    if no hand reaches the node. ``range_fraction[p]``: share of the hands
    dealt to p that are still there; ``range_combos[p]`` the same in combos.
    """

    node_id: str
    actor: Position
    reached: bool
    frequencies: tuple[float, ...] | None
    range_fraction: Triple
    range_combos: Triple
    pot: float


@dataclass(frozen=True)
class TerminalView:
    """End of a line (US2 scenario 4): pot and mean EV of each player, in bb (D-007).

    ``ev[p]`` averages p's hands weighted by how often they get there; it is
    None when the terminal is never reached.
    """

    node_id: str
    kind: TerminalKind
    reached: bool
    pot: float
    contributions: Triple
    folded: tuple[bool, bool, bool]
    ev: tuple[float | None, float | None, float | None]


@dataclass(frozen=True)
class NearestSolution:
    """Solution at the requested depth (``exact``) or at the closest one."""

    summary: SolutionSummary
    exact: bool


def _triple(values: Sequence[float]) -> Triple:
    return float(values[0]), float(values[1]), float(values[2])


def _weights(solution: Solution, node_id: str, player: int) -> NDArray[np.float64]:
    """reach · opponent mass of each class of ``player``; zero where undefined."""
    values = solution.values
    weights = values.reach_at(node_id)[player] * values.opponent_mass_at(node_id)[player]
    return np.where(np.isfinite(weights) & (weights > 0), weights, 0.0)


def node_summary(solution: Solution, node_id: str) -> NodeSummary:
    """Summary of a decision node; ``KeyError`` if unknown, ``ValueError`` if terminal."""
    node = solution.tree.node(node_id)
    if node.actor is None:
        raise ValueError(f"node {node_id!r} is a terminal: it has no strategy")
    weights = _weights(solution, node_id, int(node.actor))
    total = float(weights.sum())
    frequencies: tuple[float, ...] | None = None
    if total > 0:
        strategy = solution.strategy[node_id]  # shape (actions, classes)
        frequencies = tuple(float(f) for f in (strategy @ weights) / total)
    reach = solution.values.reach_at(node_id)
    mass = solution.hand_mass
    fractions = [float(mass @ reach[p]) / float(mass.sum()) for p in range(N_PLAYERS)]
    return NodeSummary(
        node_id=node_id,
        actor=node.actor,
        reached=frequencies is not None,
        frequencies=frequencies,
        range_fraction=_triple(fractions),
        range_combos=_triple([f * N_COMBOS for f in fractions]),
        pot=node.pot,
    )


def terminal_view(solution: Solution, node_id: str) -> TerminalView:
    """View of a terminal; ``KeyError`` if unknown, ``ValueError`` if a decision node."""
    node = solution.tree.node(node_id)
    if node.terminal is None:
        raise ValueError(f"node {node_id!r} is a decision node, not a terminal")
    ev = solution.values.ev_at(node_id)
    means: list[float | None] = []
    for player in range(N_PLAYERS):
        weights = _weights(solution, node_id, player)
        total = float(weights.sum())
        means.append(float(weights @ np.nan_to_num(ev[player])) / total if total > 0 else None)
    return TerminalView(
        node_id=node_id,
        kind=node.terminal,
        reached=all(m is not None for m in means),
        pot=node.pot,
        contributions=_triple(node.contributions),
        folded=node.folded,
        ev=(means[0], means[1], means[2]),
    )


def nearest_solution(summaries: Sequence[SolutionSummary], stack: float) -> NearestSolution | None:
    """Solution at ``stack`` bb or, if absent, at the closest depth (US1 scenario 4, D-018).

    The depth of a solution is its smallest stack. Ties between two depths go
    to the lower one; several solutions at one depth, to the most recent.
    None if ``summaries`` is empty.
    """
    if not (math.isfinite(stack) and stack > 0):
        raise ValueError(f"stack must be a positive number of bb, got {stack}")
    if not summaries:
        return None

    def key(summary: SolutionSummary) -> tuple[float, float]:
        depth = min(summary.stacks)
        return abs(depth - stack), depth

    best_key = min(key(s) for s in summaries)
    candidates = [s for s in summaries if key(s) == best_key]
    chosen = max(candidates, key=lambda s: s.created_at)
    return NearestSolution(summary=chosen, exact=best_key[0] == 0)
