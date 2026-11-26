"""Numba kernel of the fast evaluator (decision D-010).

Same logic and tables as :func:`engine.evaluator.fast.evaluate_batch`, one hand
at a time, so that tight loops (exhaustive enumeration, Monte-Carlo) can run
compiled. ``eval_masks`` and ``bit_in_suit`` are meant to be called from other
Numba kernels; :func:`evaluate_batch_numba` is the typed Python entry point.
"""

import numpy as np
from numba import njit, prange
from numpy.typing import ArrayLike, NDArray

from engine.cards import N_CARDS
from engine.evaluator.fast import POPCOUNT, STRAIGHT_HIGH, TOP_MASK, TOP_PACKED

_POP = np.ascontiguousarray(POPCOUNT, dtype=np.int64)
_SH = np.ascontiguousarray(STRAIGHT_HIGH, dtype=np.int64)
_TP = np.ascontiguousarray(TOP_PACKED, dtype=np.int64)
_TM = np.ascontiguousarray(TOP_MASK, dtype=np.int64)


@njit(cache=True, inline="always")
def bit_in_suit(card: int, suit: int) -> int:
    """Rank bit of ``card`` if it has this suit, else 0."""
    return (1 << (card >> 2)) if (card & 3) == suit else 0


@njit(cache=True, inline="always")
def eval_masks(m0: int, m1: int, m2: int, m3: int) -> int:
    """Encoded rank of the hand whose suit masks are m0..m3 (5 to 7 cards)."""
    any_ = m0 | m1 | m2 | m3
    flush = 0
    if _POP[m0] >= 5:
        flush = m0
    elif _POP[m1] >= 5:
        flush = m1
    elif _POP[m2] >= 5:
        flush = m2
    elif _POP[m3] >= 5:
        flush = m3
    if flush:
        high = _SH[flush]
        if high >= 0:
            return (8 << 20) | _TP[1, 1 << high]
    quads = m0 & m1 & m2 & m3
    if quads:
        return (7 << 20) | _TP[1, quads] | (_TP[1, any_ & ~quads] >> 4)
    ge3 = (m0 & m1 & m2) | (m0 & m1 & m3) | (m0 & m2 & m3) | (m1 & m2 & m3)
    ge2 = (m0 & m1) | (m0 & m2) | (m0 & m3) | (m1 & m2) | (m1 & m3) | (m2 & m3)
    trips = ge3 & ~quads
    pairs = ge2 & ~ge3
    if trips:
        full_pair = (trips & ~_TM[1, trips]) | pairs
        if full_pair:
            return (6 << 20) | _TP[1, trips] | (_TP[1, full_pair] >> 4)
    if flush:
        return (5 << 20) | _TP[5, flush]
    high = _SH[any_]
    if high >= 0:
        return (4 << 20) | _TP[1, 1 << high]
    if trips:
        return (3 << 20) | _TP[1, trips] | (_TP[2, any_ & ~trips] >> 4)
    if _POP[pairs] >= 2:
        return (2 << 20) | _TP[2, pairs] | (_TP[1, any_ & ~_TM[2, pairs]] >> 8)
    if pairs:
        return (1 << 20) | _TP[1, pairs] | (_TP[3, any_ & ~pairs] >> 4)
    return _TP[5, any_]


@njit(cache=True, parallel=True)
def _evaluate_rows(hands):
    out = np.empty(hands.shape[0], dtype=np.int32)
    for i in prange(hands.shape[0]):
        m0 = m1 = m2 = m3 = 0
        for j in range(hands.shape[1]):
            card = hands[i, j]
            m0 |= bit_in_suit(card, 0)
            m1 |= bit_in_suit(card, 1)
            m2 |= bit_in_suit(card, 2)
            m3 |= bit_in_suit(card, 3)
        out[i] = eval_masks(m0, m1, m2, m3)
    return out


def evaluate_batch_numba(cards: ArrayLike) -> NDArray[np.int32]:
    """Numba twin of :func:`~engine.evaluator.fast.evaluate_batch` (same values)."""
    hands = np.asarray(cards)
    if hands.ndim != 2 or not 5 <= hands.shape[1] <= 7:
        raise ValueError(f"expected shape (N, 5..7), got {hands.shape}")
    if not np.issubdtype(hands.dtype, np.integer):
        raise ValueError(f"cards must be integers, got {hands.dtype}")
    if hands.size and (hands.min() < 0 or hands.max() >= N_CARDS):
        raise ValueError("card ids must be in 0..51")
    values: NDArray[np.int32] = _evaluate_rows(np.ascontiguousarray(hands, dtype=np.int64))
    return values
