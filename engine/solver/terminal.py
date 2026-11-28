"""Terminal values of the preflop tree: fold, all-in showdown, flop (FR-007, D-002, D-007).

Tensors are indexed by hand class, each axis belonging to a seat. The
counterfactual value of hand h for player i at a terminal is

    v_i(h) = sum_{x, y} W[h, x, y] * r_j(x) * r_k(y) * u_i(h, x, y)

where W counts the card-disjoint combo triplets
(card removal), r are the per-combo reaches of the two other players (a
folded player's hand stays dead) and u_i is the net gain of i in bb since the
start of the hand, posted blinds included (D-007).

- Fold: the last live player wins the pot.
- Showdown (no more betting): main and side pots at exact equity, E3 for a
  three-way pot, E2 for a two-way pot with the third hand dead. Never any
  realization factor.
- Flop: player i gets ``R_i eq_i / sum_j R_j eq_j`` of the pot (D-002), a ratio
  computed triplet by triplet then cached for each flop context.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from engine.equity.storage import StoredEquity
from engine.game.config import Tranche
from engine.game.pots import resolve_pots
from engine.game.tree import N_PLAYERS, GameTree, Node, Position, TerminalKind
from engine.realization.profile import (
    RealizationKey,
    RealizationProfile,
    flop_positions,
    pot_type_of,
)

Tensor = NDArray[np.float64]
Reaches = Sequence[ArrayLike]
Seats = tuple[int, int, int]
"""Seat owning each axis of a tensor: ``tensor[h_s0, h_s1, h_s2]``."""

SEAT_FRAME: Final[Seats] = (0, 1, 2)
"""Axes ordered BTN, SB, BB."""

_AXIS_PERMUTATIONS: Final = ((0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
_SYMMETRY_TOLERANCE: Final = 1e-6
_MASS_CHUNK: Final = 64
"""Nodes per matrix product in ``opponent_mass`` (bounds the memory to ~15 MB)."""


def _seat_view(base: Tensor, order: tuple[int, int, int]) -> Tensor:
    """View of ``base[h_p, h_q, h_r]`` in the seat frame, for ``order = (p, q, r)``."""
    axes = tuple(int(axis) for axis in np.argsort(order))
    return base.transpose(axes)


def _readonly(array: Tensor) -> Tensor:
    array.flags.writeable = False
    return array


def _normalized_shares(shares: Tensor, total: Tensor, mask: NDArray[np.bool_]) -> Tensor:
    if not (total[mask] > 0).all():
        raise ValueError("every possible triplet needs a positive equity sum")
    out = np.zeros_like(shares)
    np.divide(shares, total, out=out, where=mask)
    return out


@dataclass(frozen=True)
class EquityTables:
    """W, E3 and E2 in float64, ready for the terminal values.

    Impossible triplets (W = 0) hold 0 instead of NaN, and the shares of each
    triplet are renormalized to sum exactly to 1, so that every terminal is
    exactly zero-sum. ``we3`` and ``we2`` are the products W * E3 and W * E2.
    """

    w: Tensor = field(repr=False)
    e3: Tensor = field(repr=False)
    e2: Tensor = field(repr=False)
    we3: Tensor = field(repr=False)
    we2: Tensor = field(repr=False)

    @property
    def n_classes(self) -> int:
        return int(self.w.shape[0])

    @classmethod
    def from_arrays(cls, w: ArrayLike, e3: ArrayLike, e2: ArrayLike) -> "EquityTables":
        """Check, clean and renormalize raw tensors of shape (n, n, n).

        ``e3[a, b, c]``: share of a in a three-way pot against b and c;
        ``e2[a, b, c]``: share of a against b, the hand of c being dead.
        """
        weights = np.asarray(w, dtype=np.float64)
        raw3 = np.asarray(e3, dtype=np.float64)
        raw2 = np.asarray(e2, dtype=np.float64)
        n = weights.shape[0] if weights.ndim == 3 else -1
        if n < 1 or any(t.shape != (n, n, n) for t in (weights, raw3, raw2)):
            raise ValueError(
                f"W, E3 and E2 must share a shape (n, n, n), got "
                f"{weights.shape}, {raw3.shape}, {raw2.shape}"
            )
        if (weights < 0).any() or not np.isfinite(weights).all():
            raise ValueError("W must be finite and non-negative")
        if any(not np.array_equal(weights, weights.transpose(p)) for p in _AXIS_PERMUTATIONS):
            raise ValueError("W must be symmetric under any permutation of its axes")

        mask = weights > 0
        clean3 = np.where(mask, raw3, 0.0)
        clean2 = np.where(mask, raw2, 0.0)
        if not (np.isfinite(clean3).all() and np.isfinite(clean2).all()):
            raise ValueError("E3 and E2 must be finite on every possible triplet")
        if not np.allclose(clean3, clean3.transpose(0, 2, 1), rtol=0, atol=_SYMMETRY_TOLERANCE):
            raise ValueError("E3 must be symmetric in its two opponents")

        # e3[a,b,c] + e3[b,a,c] + e3[c,a,b] and e2[a,b,c] + e2[b,a,c] must be 1
        total3 = clean3 + clean3.transpose(1, 0, 2) + clean3.transpose(1, 2, 0)
        total2 = clean2 + clean2.transpose(1, 0, 2)
        norm3 = _normalized_shares(clean3, total3, mask)
        norm2 = _normalized_shares(clean2, total2, mask)
        return cls(
            w=_readonly(weights),
            e3=_readonly(norm3),
            e2=_readonly(norm2),
            we3=_readonly(weights * norm3),
            we2=_readonly(weights * norm2),
        )

    @classmethod
    def from_stored(cls, stored: StoredEquity) -> "EquityTables":
        """Tables of a tensor set loaded by ``engine.equity.storage.load_tensors``."""
        return cls.from_arrays(stored.w, stored.e3, stored.e2)


def _others(player: int) -> tuple[int, int]:
    j, k = (p for p in range(N_PLAYERS) if p != player)
    return j, k


class TerminalValues:
    """Counterfactual values and expected values at the terminals of a tree."""

    def __init__(self, tree: GameTree, tables: EquityTables, profile: RealizationProfile) -> None:
        self._tree = tree
        self._tables = tables
        self._profile = profile
        self._tranche: Tranche = tree.config.tranche
        self._flop_shares: dict[tuple[tuple[int, ...], int], dict[int, Tensor]] = {}

    @property
    def n_classes(self) -> int:
        return self._tables.n_classes

    def hand_mass(self) -> Tensor:
        """Number of combo triplets in which a player holds each class (W summed)."""
        return self._tables.w.sum(axis=(1, 2))

    def opponent_mass(self, player: Position, reaches: Tensor) -> Tensor:
        """m_i(h) = sum_{x, y} W[h, x, y] r_j(x) r_k(y) at many nodes at once.

        ``reaches`` has shape (nodes, players, classes); the result (nodes,
        classes) is the weight of the opponents' hands still possible when
        ``player`` holds h: dividing a counterfactual value by it gives an EV.
        """
        n = self.n_classes
        if reaches.ndim != 3 or reaches.shape[1:] != (N_PLAYERS, n):
            raise ValueError(f"reaches must have shape (nodes, 3, {n}), got {reaches.shape}")
        j, k = _others(int(player))
        flat = self._tables.w.reshape(n, n * n)  # W is symmetric: any seat order
        result = np.empty((reaches.shape[0], n))
        for start in range(0, reaches.shape[0], _MASS_CHUNK):
            chunk = reaches[start : start + _MASS_CHUNK]
            weights = chunk[:, j, :, None] * chunk[:, k, None, :]
            result[start : start + len(chunk)] = (flat @ weights.reshape(len(chunk), n * n).T).T
        return result

    def _reaches(self, reaches: Reaches) -> tuple[Tensor, Tensor, Tensor]:
        if len(reaches) != N_PLAYERS:
            raise ValueError(f"one reach vector per player is needed, got {len(reaches)}")
        arrays = tuple(np.asarray(r, dtype=np.float64) for r in reaches)
        for array in arrays:
            if array.shape != (self.n_classes,):
                raise ValueError(f"reaches must have shape ({self.n_classes},), got {array.shape}")
        return arrays[0], arrays[1], arrays[2]

    def _terminal(self, node_id: str) -> Node:
        node = self._tree.node(node_id)
        if node.terminal is None:
            raise ValueError(f"node {node_id!r} is not a terminal")
        return node

    @staticmethod
    def _contract(
        tensor: Tensor, seats: Seats, player: int, reaches: tuple[Tensor, Tensor, Tensor]
    ) -> Tensor:
        """Sum over the two opponents' hands of tensor * their reaches, per hand of player.

        ``tensor`` is C-contiguous and ``tensor[h_s0, h_s1, h_s2]`` for
        ``seats = (s0, s1, s2)``. Every case is a matrix-vector product on the
        flattened tensor, without any copy (benchmarks/bench_terminal.py).
        """
        n = tensor.shape[0]
        flat = tensor.reshape(n, n * n)
        s0, s1, s2 = seats
        position = seats.index(player)
        if position == 0:
            result = flat @ np.outer(reaches[s1], reaches[s2]).ravel()
        elif position == 1:
            result = (reaches[s0] @ flat).reshape(n, n) @ reaches[s2]
        else:
            result = reaches[s1] @ (reaches[s0] @ flat).reshape(n, n)
        return result

    def _payoff_terms(self, node: Node, player: int) -> list[tuple[float, Tensor, Seats]]:
        """u_i as a sum of amount * tensor, contributions included (D-007)."""
        tables = self._tables
        j, k = _others(player)
        own: Seats = (player, j, k)
        terms: list[tuple[float, Tensor, Seats]] = [(-node.contributions[player], tables.w, own)]
        live = tuple(p for p in range(N_PLAYERS) if not node.folded[p])

        if node.terminal is TerminalKind.FOLD:
            if player in live:
                terms.append((node.pot, tables.w, own))
        elif node.terminal is TerminalKind.SHOWDOWN:
            for pot in resolve_pots(node.contributions, node.folded):
                if player not in pot.eligible:
                    continue
                if len(pot.eligible) == 1:
                    terms.append((pot.amount, tables.w, own))
                elif len(pot.eligible) == 3:
                    terms.append((pot.amount, tables.we3, own))
                else:
                    (other,) = pot.eligible - {player}
                    (dead,) = set(range(N_PLAYERS)) - pot.eligible
                    terms.append((pot.amount, tables.we2, (player, other, dead)))
        elif player in live:
            shares = self._flop_share_tensors(node, live)
            if player in shares:
                terms.append((node.pot, shares[player], SEAT_FRAME))
            else:  # the shares of the live players sum to W
                terms.append((node.pot, tables.w, SEAT_FRAME))
                terms.extend((-node.pot, share, SEAT_FRAME) for share in shares.values())
        return terms

    def _flop_share_tensors(self, node: Node, live: tuple[int, ...]) -> dict[int, Tensor]:
        """W * (R_i eq_i / sum_j R_j eq_j) in the seat frame, for every live player but the last.

        The last live player's tensor is W minus the others (D-002 shares sum
        to 1), which saves memory.
        """
        if any(node.stacks[p] <= 0 for p in live):
            raise NotImplementedError(
                f"node {node.id!r}: a flop with a live all-in player (side pot at the flop) "
                "is not modelled at the MVP (D-013)"
            )
        key = (live, node.raise_level)
        if key not in self._flop_shares:
            tables = self._tables
            positions = flop_positions(Position(p) for p in live)
            pot_type = pot_type_of(node.raise_level)
            if len(live) == 3:
                equities = {p: _seat_view(tables.e3, (p, *_others(p))) for p in live}
            else:
                (dead,) = set(range(N_PLAYERS)) - set(live)
                p, q = live
                equities = {
                    p: _seat_view(tables.e2, (p, q, dead)),
                    q: _seat_view(tables.e2, (q, p, dead)),
                }
            weighted = {
                p: self._profile.factor(
                    RealizationKey(len(live), pot_type, self._tranche, positions[Position(p)])
                )
                * equities[p]
                for p in live
            }
            total = sum(weighted.values())
            mask = (tables.w > 0) & (total > 0)
            shares: dict[int, Tensor] = {}
            for p in live[:-1]:
                share = np.zeros_like(tables.w)
                np.divide(weighted[p], total, out=share, where=mask)
                shares[p] = _readonly(np.ascontiguousarray(tables.w * share))
            self._flop_shares[key] = shares
        return self._flop_shares[key]

    def values(self, node_id: str, player: Position, reaches: Reaches) -> Tensor:
        """Counterfactual value v_i(h) of each hand class of ``player`` at a terminal.

        ``reaches[p]`` is the per-combo probability that player p reaches the
        node with each class. Values are not normalized: they are weighted by
        the combo counts and the opponents' reaches, as CFR needs.
        """
        node = self._terminal(node_id)
        arrays = self._reaches(reaches)
        i = int(player)
        result = np.zeros(self.n_classes)
        for amount, tensor, seats in self._merged_terms(node, i):
            result += amount * self._contract(tensor, seats, i, arrays)
        return result

    def _merged_terms(self, node: Node, player: int) -> list[tuple[float, Tensor, Seats]]:
        """Payoff terms with the amounts of a same (tensor, seats) added up, zeros dropped."""
        merged: dict[tuple[int, Seats], tuple[float, Tensor]] = {}
        for amount, tensor, seats in self._payoff_terms(node, player):
            key = (id(tensor), seats)
            previous = merged[key][0] if key in merged else 0.0
            merged[key] = (previous + amount, tensor)
        return [
            (amount, tensor, seats)
            for (_, seats), (amount, tensor) in merged.items()
            if amount != 0
        ]

    def values_batch(
        self, player: Position, reaches_by_node: Mapping[str, Reaches]
    ) -> dict[str, Tensor]:
        """``values`` at many terminals at once, with one matrix product per tensor.

        Terminals sharing a tensor (W, W*E3, W*E2, flop shares) are contracted
        together: the tensor is read once for all of them instead of once per
        terminal (benchmarks/bench_cfr.py).
        """
        i = int(player)
        n = self.n_classes
        ids = list(reaches_by_node)
        arrays = [self._reaches(reaches_by_node[node_id]) for node_id in ids]
        groups: dict[tuple[int, Seats], tuple[Tensor, list[int], list[float]]] = {}
        for column, node_id in enumerate(ids):
            for amount, tensor, seats in self._merged_terms(self._terminal(node_id), i):
                _, columns, amounts = groups.setdefault((id(tensor), seats), (tensor, [], []))
                columns.append(column)
                amounts.append(amount)

        result = np.zeros((len(ids), n))
        for (_, seats), (tensor, columns, amounts) in groups.items():
            position = seats.index(i)
            a, b = (seat for axis, seat in enumerate(seats) if axis != position)
            reach_a = np.stack([arrays[c][a] for c in columns], axis=1)
            reach_b = np.stack([arrays[c][b] for c in columns], axis=1)
            weights = reach_a[:, None, :] * reach_b[None, :, :]  # (n, n, m)
            m = len(columns)
            if position == 0:
                block = tensor.reshape(n, n * n) @ weights.reshape(n * n, m)
            elif position == 2:
                block = tensor.reshape(n * n, n).T @ weights.reshape(n * n, m)
            else:
                block = np.matmul(tensor, weights).sum(axis=0)
            result[columns] += block.T * np.asarray(amounts)[:, None]
        return {node_id: result[column] for column, node_id in enumerate(ids)}

    def expected_values(self, node_id: str, reaches: Reaches) -> tuple[float, float, float]:
        """EV of BTN, SB and BB in bb (D-007), given that the hand reaches the terminal."""
        arrays = self._reaches(reaches)
        mass = float(np.einsum("abc,a,b,c->", self._tables.w, *arrays))
        if mass <= 0:
            raise ValueError(f"node {node_id!r} cannot be reached with these reaches")
        ev = [
            float(arrays[p] @ self.values(node_id, Position(p), arrays)) / mass
            for p in range(N_PLAYERS)
        ]
        return ev[0], ev[1], ev[2]
