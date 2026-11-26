"""Naive reference hand evaluator: best 5-card hand out of 5 to 7 cards.

Deliberately slow and readable. It is the independent reference against which
the fast evaluator is checked; do not optimise it.
"""

from collections import Counter
from collections.abc import Sequence
from enum import IntEnum
from itertools import combinations
from typing import NamedTuple

from engine.cards import N_CARDS, card_rank, card_suit

ACE = 12
WHEEL_RANKS = frozenset({ACE, 0, 1, 2, 3})  # A-2-3-4-5
WHEEL_HIGH = 3  # the wheel is a five-high straight


class HandCategory(IntEnum):
    """Poker hand categories, from weakest to strongest."""

    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


class HandRank(NamedTuple):
    """Strength of a 5-card hand; compares lexicographically.

    ``kickers`` lists the ranks (0=2 .. 12=A) that break ties inside the
    category, most significant first.
    """

    category: HandCategory
    kickers: tuple[int, ...]


KICKER_BITS = 4  # one hex digit per kicker rank (0..12)
MAX_KICKERS = 5
CATEGORY_SHIFT = KICKER_BITS * MAX_KICKERS  # 20


def encode_rank(rank: HandRank) -> int:
    """Pack a hand rank into an int that preserves its order.

    ``category * 16**5 + k1 * 16**4 + ... + k5``, unused kickers being 0.
    Within a category the number of kickers is fixed, so padding keeps order.
    """
    value = int(rank.category) << CATEGORY_SHIFT
    for position, kicker in enumerate(rank.kickers):
        value |= kicker << (CATEGORY_SHIFT - KICKER_BITS * (position + 1))
    return value


def _check_cards(cards: Sequence[int], allowed_counts: range) -> None:
    if len(cards) not in allowed_counts:
        raise ValueError(f"expected {allowed_counts.start}..{allowed_counts.stop - 1} cards")
    if any(not 0 <= card < N_CARDS for card in cards):
        raise ValueError(f"invalid card id in {list(cards)}")
    if len(set(cards)) != len(cards):
        raise ValueError(f"duplicate cards in {list(cards)}")


def _straight_high(ranks: Sequence[int]) -> int | None:
    """High rank of the straight formed by 5 ranks, or None."""
    distinct = set(ranks)
    if len(distinct) != 5:
        return None
    if max(distinct) - min(distinct) == 4:
        return max(distinct)
    if distinct == WHEEL_RANKS:
        return WHEEL_HIGH
    return None


def evaluate_five(cards: Sequence[int]) -> HandRank:
    """Rank exactly 5 cards."""
    _check_cards(cards, range(5, 6))
    ranks = sorted((card_rank(card) for card in cards), reverse=True)
    is_flush = len({card_suit(card) for card in cards}) == 1
    straight_high = _straight_high(ranks)

    if straight_high is not None:
        category = HandCategory.STRAIGHT_FLUSH if is_flush else HandCategory.STRAIGHT
        return HandRank(category, (straight_high,))
    if is_flush:
        return HandRank(HandCategory.FLUSH, tuple(ranks))

    # Group ranks by multiplicity, largest group first, then highest rank.
    counts = Counter(ranks)
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    shape = tuple(count for _, count in groups)
    kickers = tuple(rank for rank, _ in groups)

    category = {
        (4, 1): HandCategory.FOUR_OF_A_KIND,
        (3, 2): HandCategory.FULL_HOUSE,
        (3, 1, 1): HandCategory.THREE_OF_A_KIND,
        (2, 2, 1): HandCategory.TWO_PAIR,
        (2, 1, 1, 1): HandCategory.PAIR,
        (1, 1, 1, 1, 1): HandCategory.HIGH_CARD,
    }[shape]
    return HandRank(category, kickers)


def evaluate(cards: Sequence[int]) -> HandRank:
    """Best 5-card hand rank among 5 to 7 cards (tries every 5-card subset)."""
    _check_cards(cards, range(5, 8))
    return max(evaluate_five(subset) for subset in combinations(cards, 5))


def compare(hand_a: Sequence[int], hand_b: Sequence[int], board: Sequence[int]) -> int:
    """Showdown result for ``hand_a``: +1 win, -1 loss, 0 split.

    Each hand has 2 hole cards; the board has 5 cards.
    """
    if len(hand_a) != 2 or len(hand_b) != 2:
        raise ValueError("each hand needs exactly 2 hole cards")
    if len(board) != 5:
        raise ValueError("the board needs exactly 5 cards")
    _check_cards([*hand_a, *hand_b, *board], range(9, 10))
    rank_a = evaluate([*hand_a, *board])
    rank_b = evaluate([*hand_b, *board])
    return (rank_a > rank_b) - (rank_a < rank_b)
