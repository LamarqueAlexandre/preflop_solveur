"""Fast vectorised evaluator: best 5-card hand of 5 to 7 cards, for N hands at once.

Each hand is described by 13-bit rank masks (bit r set = rank r present):
one mask per suit, from which the masks of ranks held at least 1, 2, 3 or
4 times follow by bitwise logic. Small 8192-entry tables then give popcounts,
straights and packed kickers. Values use the encoding of
:func:`engine.evaluator.reference.encode_rank`, so they compare like
:class:`~engine.evaluator.reference.HandRank`.
"""

from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from engine.cards import N_CARDS, N_RANKS, N_SUITS
from engine.evaluator.reference import (
    CATEGORY_SHIFT,
    KICKER_BITS,
    MAX_KICKERS,
    HandCategory,
)

N_MASKS: Final = 1 << N_RANKS  # 8192
_WHEEL_MASK: Final = 0b1_0000_0000_1111  # A, 2, 3, 4, 5
_WHEEL_HIGH: Final = 3  # five-high


def _build_tables() -> tuple[
    NDArray[np.int32], NDArray[np.int32], NDArray[np.int32], NDArray[np.int32]
]:
    """Return POPCOUNT, STRAIGHT_HIGH, TOP_PACKED[k] and TOP_MASK[k] (k = 0..5)."""
    popcount = np.zeros(N_MASKS, dtype=np.int32)
    straight_high = np.full(N_MASKS, -1, dtype=np.int32)
    top_packed = np.zeros((MAX_KICKERS + 1, N_MASKS), dtype=np.int32)
    top_mask = np.zeros((MAX_KICKERS + 1, N_MASKS), dtype=np.int32)
    for mask in range(N_MASKS):
        ranks_desc = [r for r in reversed(range(N_RANKS)) if mask >> r & 1]
        popcount[mask] = len(ranks_desc)
        for high in reversed(range(4, N_RANKS)):
            run = 0b11111 << (high - 4)
            if mask & run == run:
                straight_high[mask] = high
                break
        else:
            if mask & _WHEEL_MASK == _WHEEL_MASK:
                straight_high[mask] = _WHEEL_HIGH
        for k in range(1, MAX_KICKERS + 1):
            top = ranks_desc[:k]
            top_packed[k, mask] = sum(
                rank << (CATEGORY_SHIFT - KICKER_BITS * (i + 1)) for i, rank in enumerate(top)
            )
            top_mask[k, mask] = sum(1 << rank for rank in top)
    return popcount, straight_high, top_packed, top_mask


POPCOUNT, STRAIGHT_HIGH, TOP_PACKED, TOP_MASK = _build_tables()
for _table in (POPCOUNT, STRAIGHT_HIGH, TOP_PACKED, TOP_MASK):
    _table.flags.writeable = False


def _category(category: HandCategory) -> int:
    return int(category) << CATEGORY_SHIFT


def _shift(packed: NDArray[np.int32], slots: int) -> NDArray[np.int32]:
    """Move packed kickers ``slots`` positions to the right (less significant)."""
    return packed >> (KICKER_BITS * slots)


def evaluate_batch(cards: ArrayLike) -> NDArray[np.int32]:
    """Evaluate N hands of 5 to 7 cards; ``cards`` has shape (N, k).

    Returns the encoded rank of each hand (shape (N,), int32); higher is better.
    Cards within a row must be distinct: this is not checked, for speed.
    """
    hands = np.asarray(cards)
    if hands.ndim != 2 or not 5 <= hands.shape[1] <= 7:
        raise ValueError(f"expected shape (N, 5..7), got {hands.shape}")
    if not np.issubdtype(hands.dtype, np.integer):
        raise ValueError(f"cards must be integers, got {hands.dtype}")
    if hands.size and (hands.min() < 0 or hands.max() >= N_CARDS):
        raise ValueError("card ids must be in 0..51")

    hands = hands.astype(np.int32)
    bits = np.left_shift(1, hands // N_SUITS, dtype=np.int32)
    suits = hands % N_SUITS
    m0, m1, m2, m3 = (
        np.bitwise_or.reduce(np.where(suits == s, bits, 0), axis=1) for s in range(N_SUITS)
    )

    # Ranks held at least 1, 2, 3 and 4 times (one card per suit and rank).
    any_ = m0 | m1 | m2 | m3
    ge2 = (m0 & m1) | (m0 & m2) | (m0 & m3) | (m1 & m2) | (m1 & m3) | (m2 & m3)
    ge3 = (m0 & m1 & m2) | (m0 & m1 & m3) | (m0 & m2 & m3) | (m1 & m2 & m3)
    quads = m0 & m1 & m2 & m3
    trips = ge3 & ~quads
    pairs = ge2 & ~ge3

    # With at most 7 cards, at most one suit can hold 5 or more.
    flush = np.zeros_like(any_)
    for mask in (m0, m1, m2, m3):
        flush |= np.where(POPCOUNT[mask] >= 5, mask, 0)

    top1 = TOP_PACKED[1]
    sf_high = STRAIGHT_HIGH[flush]
    straight_high = STRAIGHT_HIGH[any_]
    top_trip = TOP_MASK[1][trips]
    full_pair = (trips & ~top_trip) | pairs  # a second trips counts as the pair
    top_two_pairs = TOP_MASK[2][pairs]

    conditions = [
        sf_high >= 0,
        quads != 0,
        (trips != 0) & (full_pair != 0),
        flush != 0,
        straight_high >= 0,
        trips != 0,
        POPCOUNT[pairs] >= 2,
        pairs != 0,
    ]
    choices = [
        _category(HandCategory.STRAIGHT_FLUSH) | top1[1 << np.maximum(sf_high, 0)],
        _category(HandCategory.FOUR_OF_A_KIND) | top1[quads] | _shift(top1[any_ & ~quads], 1),
        _category(HandCategory.FULL_HOUSE) | top1[trips] | _shift(top1[full_pair], 1),
        _category(HandCategory.FLUSH) | TOP_PACKED[5][flush],
        _category(HandCategory.STRAIGHT) | top1[1 << np.maximum(straight_high, 0)],
        _category(HandCategory.THREE_OF_A_KIND)
        | top1[trips]
        | _shift(TOP_PACKED[2][any_ & ~trips], 1),
        _category(HandCategory.TWO_PAIR)
        | TOP_PACKED[2][pairs]
        | _shift(top1[any_ & ~top_two_pairs], 2),
        _category(HandCategory.PAIR) | top1[pairs] | _shift(TOP_PACKED[3][any_ & ~pairs], 1),
    ]
    default = _category(HandCategory.HIGH_CARD) | TOP_PACKED[5][any_]
    values: NDArray[np.int32] = np.select(conditions, choices, default=default).astype(np.int32)
    return values


def category_of(values: ArrayLike) -> NDArray[np.int32]:
    """Hand category (0..8) of encoded values."""
    encoded: NDArray[np.int64] = np.asarray(values, dtype=np.int64)
    return np.right_shift(encoded, CATEGORY_SHIFT).astype(np.int32)
