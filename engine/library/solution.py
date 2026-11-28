"""A solved configuration: average strategy, EVs and reaches at every node (FR-009, FR-011).

``solve`` runs Discounted CFR by blocks of ``check_every`` iterations and
measures NashConv after each block; it stops at the first check below
``target_percent`` or at ``max_iterations`` (D-015). EVs and reaches are those
of the average strategy, the one that converges and is published.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from engine.game.config import GameConfig
from engine.game.tree import N_PLAYERS, Action, GameTree, Position
from engine.realization.profile import RealizationProfile
from engine.solver import (
    PUBLICATION_THRESHOLD_PERCENT,
    DCFRParams,
    DCFRSolver,
    EquityTables,
    Exploitability,
    NodeValues,
    Strategy,
    TerminalValues,
    exploitability,
    node_values,
)

Progress = Callable[[int, Exploitability], None]
"""Called after each convergence check with the iteration count and NashConv."""


@dataclass(frozen=True)
class SolveParams:
    """Convergence parameters (D-015); they belong to the fingerprint of a solution (FR-012)."""

    max_iterations: int = 2000
    target_percent: float = 0.1
    check_every: int = 100
    dcfr: DCFRParams = field(default_factory=DCFRParams)

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be positive, got {self.max_iterations}")
        if self.check_every < 1:
            raise ValueError(f"check_every must be positive, got {self.check_every}")
        if not self.target_percent > 0:
            raise ValueError(f"target_percent must be positive, got {self.target_percent}")


@dataclass(frozen=True)
class NodeSolution:
    """What a decision node shows: arrays over the hand classes.

    ``strategy`` and ``action_ev`` (EV of the actor for each action) have
    shape (actions, classes); ``ev`` and ``reach`` have shape (players, classes).
    """

    node_id: str
    actor: Position
    actions: tuple[Action, ...]
    strategy: Strategy = field(repr=False)
    action_ev: NDArray[np.float64] = field(repr=False)
    ev: NDArray[np.float64] = field(repr=False)
    reach: NDArray[np.float64] = field(repr=False)


@dataclass(frozen=True)
class Solution:
    """Equilibrium of one configuration, with how it was computed."""

    tree: GameTree = field(repr=False)
    profile_name: str
    profile_version: str
    params: SolveParams
    iterations: int
    duration_seconds: float
    exploitability: Exploitability
    strategy: Mapping[str, Strategy] = field(repr=False)
    values: NodeValues = field(repr=False)
    hand_mass: NDArray[np.float64] = field(repr=False)

    @property
    def config(self) -> GameConfig:
        return self.tree.config

    @property
    def publishable(self) -> bool:
        """NashConv below 0.5% of the starting pot (FR-010, D-001)."""
        return self.exploitability.percent < PUBLICATION_THRESHOLD_PERCENT

    def root_ev(self) -> tuple[float, float, float]:
        """EV of BTN, SB and BB per hand dealt, in bb (D-007)."""
        root = self.values.ev_at(self.tree.root.id)
        total = float(self.hand_mass.sum())
        ev = [float(self.hand_mass @ root[p]) / total for p in range(N_PLAYERS)]
        return ev[0], ev[1], ev[2]

    def node(self, node_id: str) -> NodeSolution:
        """View of a decision node; ``KeyError`` if unknown, ``ValueError`` if terminal."""
        node = self.tree.node(node_id)
        if node.actor is None:
            raise ValueError(f"node {node_id!r} is a terminal: it has no strategy")
        actor = int(node.actor)
        action_ev = np.stack([self.values.ev_at(child)[actor] for child in node.children])
        action_ev.flags.writeable = False
        return NodeSolution(
            node_id=node_id,
            actor=node.actor,
            actions=node.actions,
            strategy=self.strategy[node_id],
            action_ev=action_ev,
            ev=self.values.ev_at(node_id),
            reach=self.values.reach_at(node_id),
        )


def solve(
    tree: GameTree,
    tables: EquityTables,
    profile: RealizationProfile,
    params: SolveParams | None = None,
    progress: Progress | None = None,
) -> Solution:
    """Solve ``tree`` until NashConv < ``target_percent`` or ``max_iterations`` (D-015)."""
    params = params or SolveParams()
    if profile.name != tree.config.realization_profile:
        raise ValueError(
            f"the config names realization profile {tree.config.realization_profile!r}, "
            f"got profile {profile.name!r}"
        )
    start = time.perf_counter()
    values = TerminalValues(tree, tables, profile)
    solver = DCFRSolver(tree, values, params.dcfr)
    while True:
        solver.iterate(min(params.check_every, params.max_iterations - solver.iterations))
        average = solver.average_strategy()
        measured = exploitability(tree, values, average)
        if progress is not None:
            progress(solver.iterations, measured)
        if measured.percent < params.target_percent or solver.iterations >= params.max_iterations:
            break

    for played in average.values():
        played.flags.writeable = False
    result = node_values(tree, values, average)
    return Solution(
        tree=tree,
        profile_name=profile.name,
        profile_version=profile.version,
        params=params,
        iterations=solver.iterations,
        duration_seconds=time.perf_counter() - start,
        exploitability=measured,
        strategy=average,
        values=result,
        hand_mass=values.hand_mass(),
    )
