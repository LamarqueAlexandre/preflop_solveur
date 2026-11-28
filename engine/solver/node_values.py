"""Reaches and conditional EVs at every node of a strategy profile (FR-011, US2).

The solver works with counterfactual values: summed over the opponents' hands,
weighted by the combo counts W and by the opponents' reaches. The EV shown to
a player divides them by the weight of the opponent hands still possible
(Bayes), giving the expected net gain in bb of holding h at the node (D-007):

    EV_i(n, h) = v_i(n, h) / m_i(n, h),  m_i(n, h) = sum_{x,y} W[h,x,y] r_j(n,x) r_k(n,y)

It is NaN where m_i = 0: the opponents never get there. For the actor, an
action leaves the opponents' reaches unchanged, so the EV of a node is the
strategy-weighted EV of its actions. See docs/notes/solution-ev.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from engine.game.tree import N_PLAYERS, GameTree, Position
from engine.solver._traversal import Strategy, TreeIndex
from engine.solver.terminal import TerminalValues


def _readonly(array: NDArray[np.float64]) -> NDArray[np.float64]:
    array.flags.writeable = False
    return array


@dataclass(frozen=True)
class NodeValues:
    """Per-node arrays of shape (nodes, players, classes), nodes in ``node_ids`` order.

    ``reach[n, p, h]``: probability that p plays to n with h (own actions only).
    ``opponent_mass[n, p, h]``: weight of the opponent hands still possible.
    ``ev[n, p, h]``: EV of p holding h at n, in bb (NaN if undefined).
    """

    node_ids: tuple[str, ...]
    reach: NDArray[np.float64] = field(repr=False)
    opponent_mass: NDArray[np.float64] = field(repr=False)
    ev: NDArray[np.float64] = field(repr=False)
    _index: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", {node_id: k for k, node_id in enumerate(self.node_ids)})

    def index(self, node_id: str) -> int:
        """Row of a node in the arrays; ``KeyError`` if unknown."""
        return self._index[node_id]

    def reach_at(self, node_id: str) -> NDArray[np.float64]:
        """Shape (players, classes)."""
        row: NDArray[np.float64] = self.reach[self.index(node_id)]
        return row

    def opponent_mass_at(self, node_id: str) -> NDArray[np.float64]:
        """Shape (players, classes)."""
        row: NDArray[np.float64] = self.opponent_mass[self.index(node_id)]
        return row

    def ev_at(self, node_id: str) -> NDArray[np.float64]:
        """Shape (players, classes)."""
        row: NDArray[np.float64] = self.ev[self.index(node_id)]
        return row


def _counterfactual_values(
    index: TreeIndex,
    values: TerminalValues,
    strategies: Mapping[int, Strategy],
    reaches: NDArray[np.float64],
    player: int,
) -> NDArray[np.float64]:
    """v_player(n, h) at every node, going up from the terminals."""
    result = index.terminal_values(values, player, reaches)
    for k in reversed(index.decisions):
        children = index.children[k]
        if index.actors[k] == player:
            result[k] = (strategies[k] * result[children]).sum(axis=0)
        else:
            result[k] = result[children].sum(axis=0)
    return result


def node_values(
    tree: GameTree, terminal_values: TerminalValues, profile: Mapping[str, Strategy]
) -> NodeValues:
    """Reaches, opponent masses and conditional EVs of ``profile`` at every node."""
    index = TreeIndex(tree)
    n_classes = terminal_values.n_classes
    strategies = index.check_profile(profile, n_classes)
    reaches = index.reaches(strategies, n_classes)

    mass = np.empty_like(reaches)
    ev = np.empty_like(reaches)
    for player in range(N_PLAYERS):
        counterfactual = _counterfactual_values(index, terminal_values, strategies, reaches, player)
        mass[:, player] = terminal_values.opponent_mass(Position(player), reaches)
        reached = mass[:, player] > 0
        ev[:, player] = np.nan
        np.divide(counterfactual, mass[:, player], out=ev[:, player], where=reached)

    return NodeValues(
        node_ids=tuple(index.ids),
        reach=_readonly(reaches),
        opponent_mass=_readonly(mass),
        ev=_readonly(ev),
    )
