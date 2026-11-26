"""Tests for the fast vectorised evaluator, checked against the reference one."""

from collections.abc import Iterator
from itertools import combinations
from math import comb

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from engine.cards import RANK_CHARS, parse_card
from engine.evaluator import (
    HandCategory,
    HandRank,
    category_of,
    encode_rank,
    evaluate,
    evaluate_batch,
)


def cards(text: str) -> list[int]:
    """Parse space-separated cards, e.g. ``"Ah Kd Qs"``."""
    return [parse_card(token) for token in text.split()]


def ranks(text: str) -> tuple[int, ...]:
    """Rank indices of a string of rank characters, e.g. ``"AKQ"``."""
    return tuple(RANK_CHARS.index(char) for char in text)


def fast_value(hand: list[int]) -> int:
    """Fast evaluation of a single hand."""
    return int(evaluate_batch(np.array([hand]))[0])


# --- Shared integer encoding of a HandRank -------------------------------------


def test_encode_rank_packs_category_then_kickers() -> None:
    # Full house K-K-K-4-4: 6 * 16**5 + 11 * 16**4 + 2 * 16**3 = 7_020_544.
    expected = 6 * 16**5 + 11 * 16**4 + 2 * 16**3
    assert expected == 7_020_544
    assert encode_rank(HandRank(HandCategory.FULL_HOUSE, ranks("K4"))) == expected


def test_encode_rank_of_a_wheel() -> None:
    assert encode_rank(HandRank(HandCategory.STRAIGHT, ranks("5"))) == 4 * 16**5 + 3 * 16**4


ORDERED_RANKS = [
    HandRank(HandCategory.HIGH_CARD, ranks("75432")),
    HandRank(HandCategory.HIGH_CARD, ranks("AKQJ9")),
    HandRank(HandCategory.PAIR, ranks("2543")),
    HandRank(HandCategory.PAIR, ranks("AKQJ")),
    HandRank(HandCategory.TWO_PAIR, ranks("322")),
    HandRank(HandCategory.TWO_PAIR, ranks("AKQ")),
    HandRank(HandCategory.THREE_OF_A_KIND, ranks("AKQ")),
    HandRank(HandCategory.STRAIGHT, ranks("5")),
    HandRank(HandCategory.STRAIGHT, ranks("A")),
    HandRank(HandCategory.FLUSH, ranks("76432")),
    HandRank(HandCategory.FULL_HOUSE, ranks("23")),
    HandRank(HandCategory.FULL_HOUSE, ranks("AK")),
    HandRank(HandCategory.FOUR_OF_A_KIND, ranks("AK")),
    HandRank(HandCategory.STRAIGHT_FLUSH, ranks("5")),
    HandRank(HandCategory.STRAIGHT_FLUSH, ranks("A")),
]


def test_encode_rank_preserves_order() -> None:
    assert sorted(ORDERED_RANKS) == ORDERED_RANKS
    encoded = [encode_rank(rank) for rank in ORDERED_RANKS]
    assert encoded == sorted(encoded)
    assert len(set(encoded)) == len(encoded)


def test_category_of_extracts_the_category() -> None:
    values = np.array([encode_rank(rank) for rank in ORDERED_RANKS])
    expected = [rank.category for rank in ORDERED_RANKS]
    assert category_of(values).tolist() == expected


# --- Hand-written cases: same value as the reference ---------------------------

HAND_WRITTEN = [
    # One per category.
    "Ah Jd 9c 6s 3h",
    "Kh Kd 9c 6s 3h",
    "Kh Kd 9c 9s 3h",
    "7h 7d 7c As 3h",
    "9h 8d 7c 6s 5h",
    "Ah Jh 9h 6h 3h",
    "Qh Qd Qc 4s 4h",
    "5h 5d 5c 5s Kh",
    "9h 8h 7h 6h 5h",
    "Ah Kh Qh Jh Th",
    # Straights.
    "Ah 2d 3c 4s 5h",
    "2h 3d 4c 5s 6h",
    "As 2s 3s 4s 5s",
    "Qh Kd Ac 2s 3h",
    "6d 5d 4d 3d 2d",
    "Ad Kd Qd Jd 9d",
    # 7-card traps.
    "Kh Kd Kc 7s 2h Ah Ad",
    "Kh Kd Kc 7s 2h Qh Qd",
    "9h 9d 9c 4s 4h 4d 2c",
    "Kh Kd 8c 8s 5h 5d 3c",
    "Ah Kh 9h 7h 4h 2h Qd",
    "4h 5d 6c 7s 8h 9d Kc",
    "Ah 2d 3c 4s 5h 6d Kc",
    "5h 6h 7d 8h 9c Kh 2h",
    "7h 7d 7c 7s 2h Qd Jc",
    "7h 7d 7c 7s Kh Kd 2c",
    "As Ks Qs Js 2d 7c 3s",
    "Th Td Qs Js 2d 7c 3s",
    "As 2s 3s 4s 5s 6s 7s",
    "Ah Ad As Ac Kh Kd Ks",
    # 6 cards.
    "Ah Jd 9c 6s 3h 3d",
]


@pytest.mark.parametrize("hand", HAND_WRITTEN)
def test_hand_written_cases_match_reference(hand: str) -> None:
    parsed = cards(hand)
    assert fast_value(parsed) == encode_rank(evaluate(parsed))


def test_batch_returns_one_int32_value_per_row() -> None:
    batch = np.array([cards(hand) for hand in HAND_WRITTEN if len(hand.split()) == 7])
    values = evaluate_batch(batch)
    assert values.shape == (len(batch),)
    assert values.dtype == np.int32
    assert values.tolist() == [encode_rank(evaluate(row.tolist())) for row in batch]


def test_batch_accepts_any_integer_dtype() -> None:
    batch = np.array([cards("As Ks Qs Js 2d 7c 3s")], dtype=np.uint8)
    assert evaluate_batch(batch).tolist() == [encode_rank(evaluate(batch[0].tolist()))]


def test_empty_batch() -> None:
    assert evaluate_batch(np.empty((0, 7), dtype=np.int64)).shape == (0,)


# --- Property: agreement with the reference on random hands ----------------------


@settings(max_examples=2000, deadline=None)
@given(st.lists(st.integers(0, 51), min_size=5, max_size=7, unique=True))
def test_random_hands_match_reference(hand: list[int]) -> None:
    assert fast_value(hand) == encode_rank(evaluate(hand))


def test_random_seven_card_batch_matches_reference() -> None:
    rng = np.random.default_rng(20261126)
    batch = np.array([rng.choice(52, size=7, replace=False) for _ in range(5000)])
    expected = [encode_rank(evaluate(row.tolist())) for row in batch]
    assert evaluate_batch(batch).tolist() == expected


# --- Invalid input -------------------------------------------------------------


@pytest.mark.parametrize("shape", [(7,), (3, 4), (3, 8), (2, 7, 1)])
def test_rejects_bad_shapes(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        evaluate_batch(np.zeros(shape, dtype=np.int64))


@pytest.mark.parametrize("bad_card", [-1, 52])
def test_rejects_out_of_range_cards(bad_card: int) -> None:
    with pytest.raises(ValueError):
        evaluate_batch(np.array([[*cards("Ah Kd Qc Js 2h 3d"), bad_card]]))


def test_rejects_non_integer_cards() -> None:
    with pytest.raises(ValueError):
        evaluate_batch(np.zeros((1, 7), dtype=np.float64))


# --- Exhaustive checks -----------------------------------------------------------


@pytest.mark.slow
def test_all_five_card_hands_match_reference() -> None:
    hands = np.array(list(combinations(range(52), 5)), dtype=np.int8)
    expected = np.array([encode_rank(evaluate(hand.tolist())) for hand in hands])
    np.testing.assert_array_equal(evaluate_batch(hands), expected)


# Source: https://en.wikipedia.org/wiki/Poker_probability (7-card hands).
EXPECTED_SEVEN_CARD_COUNTS = {
    HandCategory.STRAIGHT_FLUSH: 41_584,
    HandCategory.FOUR_OF_A_KIND: 224_848,
    HandCategory.FULL_HOUSE: 3_473_184,
    HandCategory.FLUSH: 4_047_644,
    HandCategory.STRAIGHT: 6_180_020,
    HandCategory.THREE_OF_A_KIND: 6_461_620,
    HandCategory.TWO_PAIR: 31_433_400,
    HandCategory.PAIR: 58_627_800,
    HandCategory.HIGH_CARD: 23_294_460,
}


def all_seven_card_hands() -> Iterator[NDArray[np.int8]]:
    """Yield every 7-card hand exactly once, in chunks sharing their two lowest cards."""
    # 5-card subsets of range(50) sorted by their largest card: the subsets of
    # range(m) are then exactly the first comb(m, 5) rows.
    tails = np.array(list(combinations(range(50), 5)), dtype=np.int8)
    tails = tails[np.argsort(tails[:, 4], kind="stable")]
    for low in range(52):
        for second in range(low + 1, 52):
            n_tails = comb(51 - second, 5)
            if n_tails == 0:
                continue
            chunk = np.empty((n_tails, 7), dtype=np.int8)
            chunk[:, 0] = low
            chunk[:, 1] = second
            chunk[:, 2:] = tails[:n_tails] + (second + 1)
            yield chunk


@pytest.mark.slow
def test_all_seven_card_hands_match_published_counts() -> None:
    category_counts = np.zeros(len(HandCategory), dtype=np.int64)
    distinct_values: set[int] = set()
    n_hands = 0
    for chunk in all_seven_card_hands():
        values = evaluate_batch(chunk)
        category_counts += np.bincount(category_of(values), minlength=len(HandCategory))
        distinct_values.update(np.unique(values).tolist())
        n_hands += len(chunk)
    assert n_hands == comb(52, 7) == 133_784_560
    assert dict(zip(HandCategory, category_counts.tolist(), strict=True)) == (
        EXPECTED_SEVEN_CARD_COUNTS
    )
    assert len(distinct_values) == 4_824
