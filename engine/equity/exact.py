"""Exact (exhaustive) equities: every board, every compatible combo.

The independent reference used to validate the Monte-Carlo tensors E3 and E2
(SC-003, D-003). Combos related by a permutation of the four suits have the
same equity, so each class matchup is reduced to its suit configurations,
weighted by the number of combo tuples they stand for (D-010, spike #8).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import permutations
from typing import Final

import numpy as np
from numpy.typing import NDArray

from engine.cards import COMBOS, N_CARDS, N_CLASSES, combos_of_class
from engine.equity._kernels import board_sums, configuration_means

PAIRS: Final = ((0, 1), (0, 2), (1, 2))
"""Order of the heads-up results of a three-way matchup."""

_SUIT_PERMUTATIONS: Final = np.array(list(permutations(range(4))), dtype=np.int64)


@dataclass(frozen=True)
class ThreeWayEquity:
    """Exact equities of a three-class matchup.

    ``three_way[p]``: pot share of player p when all three go to showdown.
    ``heads_up[k]``: share of the first player of ``PAIRS[k]`` against the
    second, the third player's hand being removed from the deck (dead).
    """

    three_way: tuple[float, float, float]
    heads_up: tuple[float, float, float]


def _check_classes(classes: Sequence[int]) -> None:
    for index in classes:
        if not 0 <= index < N_CLASSES:
            raise ValueError(f"invalid class index: {index}")


def suit_configurations(
    classes: Sequence[int],
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Card-disjoint combo tuples of these classes, grouped up to a suit permutation.

    Returns ``(representatives, weights)``: one row of cards (2 per player)
    per configuration, and the number of combo tuples each one stands for.
    The weights sum to the number of compatible combo tuples (W for 3 classes).
    """
    _check_classes(classes)
    hands = [COMBOS[combos_of_class(c)].astype(np.int64) for c in classes]
    grid = np.meshgrid(*(np.arange(len(h)) for h in hands), indexing="ij")
    rows = np.concatenate([h[g.ravel()] for h, g in zip(hands, grid, strict=True)], axis=1)
    rows = rows[np.all(np.diff(np.sort(rows, axis=1), axis=1) > 0, axis=1)]
    if len(rows) == 0:
        return rows, np.zeros(0, dtype=np.int64)

    ranks, suits = rows // 4, rows % 4
    canonical = np.full(len(rows), np.iinfo(np.int64).max)
    for perm in _SUIT_PERMUTATIONS:
        permuted = ranks * 4 + perm[suits]
        key = np.zeros(len(rows), dtype=np.int64)
        for player in range(len(classes)):
            a, b = permuted[:, 2 * player], permuted[:, 2 * player + 1]
            key = key * (N_CARDS * N_CARDS) + np.minimum(a, b) * N_CARDS + np.maximum(a, b)
        canonical = np.minimum(canonical, key)
    _, first, weights = np.unique(canonical, return_index=True, return_counts=True)
    return rows[first], weights.astype(np.int64)


def exact_combo_equity(
    hands: Sequence[Sequence[int]], board: Sequence[int] = ()
) -> NDArray[np.float64]:
    """Exact pot share of each hand (2 cards each) over every completion of ``board``."""
    if len(hands) < 2 or any(len(hand) != 2 for hand in hands):
        raise ValueError("expected at least 2 hands of 2 cards")
    if len(board) > 5:
        raise ValueError("a board has at most 5 cards")
    flat = [card for hand in hands for card in hand]
    all_cards = flat + list(board)
    if any(not 0 <= card < N_CARDS for card in all_cards):
        raise ValueError("card ids must be in 0..51")
    if len(set(all_cards)) != len(all_cards):
        raise ValueError("a card appears twice")
    sums, n_boards = board_sums(np.array(flat, dtype=np.int64), np.array(board, dtype=np.int64))
    shares: NDArray[np.float64] = sums[: len(hands)] / n_boards
    return shares


def _class_means(classes: Sequence[int]) -> NDArray[np.float64]:
    """Weighted mean of the per-configuration shares (n-way, then pairs)."""
    representatives, weights = suit_configurations(classes)
    if len(weights) == 0:
        raise ValueError(f"no card-disjoint combos for classes {list(classes)}")
    means = configuration_means(representatives)
    result: NDArray[np.float64] = weights @ means / weights.sum()
    return result


def heads_up_equity(h1: int, h2: int) -> tuple[float, float]:
    """Exact all-in equity of two classes against each other (no dead cards)."""
    first = float(_class_means((h1, h2))[0])
    return first, 1.0 - first


def three_way_equity(h1: int, h2: int, h3: int) -> ThreeWayEquity:
    """Exact E3 and E2 (third hand dead) of three classes, splits included."""
    means = _class_means((h1, h2, h3))
    return ThreeWayEquity(
        three_way=(float(means[0]), float(means[1]), float(means[2])),
        heads_up=(float(means[3]), float(means[4]), float(means[5])),
    )
