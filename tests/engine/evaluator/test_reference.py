"""Tests for the naive reference 7-card evaluator."""

from collections import Counter
from itertools import combinations

import pytest

from engine.cards import RANK_CHARS, parse_card
from engine.evaluator import HandCategory, HandRank, compare, evaluate, evaluate_five


def cards(text: str) -> list[int]:
    """Parse space-separated cards, e.g. ``"Ah Kd Qs"``."""
    return [parse_card(token) for token in text.split()]


def r(char: str) -> int:
    """Rank index of a rank character (``"2"`` -> 0, ``"A"`` -> 12)."""
    return RANK_CHARS.index(char)


def ranks(text: str) -> tuple[int, ...]:
    """Rank indices of a string of rank characters, e.g. ``"AKQ"``."""
    return tuple(r(char) for char in text)


# --- One hand-written case per category (5 cards) ---------------------------


@pytest.mark.parametrize(
    ("hand", "expected"),
    [
        ("Ah Jd 9c 6s 3h", HandRank(HandCategory.HIGH_CARD, ranks("AJ963"))),
        ("Kh Kd 9c 6s 3h", HandRank(HandCategory.PAIR, ranks("K963"))),
        ("Kh Kd 9c 9s 3h", HandRank(HandCategory.TWO_PAIR, ranks("K93"))),
        ("7h 7d 7c As 3h", HandRank(HandCategory.THREE_OF_A_KIND, ranks("7A3"))),
        ("9h 8d 7c 6s 5h", HandRank(HandCategory.STRAIGHT, ranks("9"))),
        ("Ah Jh 9h 6h 3h", HandRank(HandCategory.FLUSH, ranks("AJ963"))),
        ("Qh Qd Qc 4s 4h", HandRank(HandCategory.FULL_HOUSE, ranks("Q4"))),
        ("5h 5d 5c 5s Kh", HandRank(HandCategory.FOUR_OF_A_KIND, ranks("5K"))),
        ("9h 8h 7h 6h 5h", HandRank(HandCategory.STRAIGHT_FLUSH, ranks("9"))),
    ],
)
def test_each_category_is_recognised(hand: str, expected: HandRank) -> None:
    assert evaluate_five(cards(hand)) == expected


def test_categories_are_ordered_from_high_card_to_straight_flush() -> None:
    assert list(HandCategory) == sorted(HandCategory)
    assert HandCategory.HIGH_CARD == 0
    assert HandCategory.STRAIGHT_FLUSH == 8


def test_royal_flush_is_the_best_straight_flush() -> None:
    assert evaluate_five(cards("Ah Kh Qh Jh Th")) == HandRank(
        HandCategory.STRAIGHT_FLUSH, ranks("A")
    )


# --- Straights: the wheel and no wrap-around ---------------------------------


def test_wheel_is_a_five_high_straight() -> None:
    assert evaluate_five(cards("Ah 2d 3c 4s 5h")) == HandRank(HandCategory.STRAIGHT, ranks("5"))


def test_wheel_loses_to_six_high_straight() -> None:
    assert evaluate_five(cards("Ah 2d 3c 4s 5h")) < evaluate_five(cards("2h 3d 4c 5s 6h"))


def test_steel_wheel_is_a_five_high_straight_flush() -> None:
    assert evaluate_five(cards("As 2s 3s 4s 5s")) == HandRank(
        HandCategory.STRAIGHT_FLUSH, ranks("5")
    )


def test_straights_do_not_wrap_around() -> None:
    assert evaluate_five(cards("Qh Kd Ac 2s 3h")).category == HandCategory.HIGH_CARD


# --- Comparisons within a category -------------------------------------------


def test_straight_flush_beats_flush() -> None:
    assert evaluate_five(cards("6d 5d 4d 3d 2d")) > evaluate_five(cards("Ad Kd Qd Jd 9d"))


def test_full_house_is_decided_by_trips_first() -> None:
    assert evaluate_five(cards("3h 3d 3c 2s 2h")) > evaluate_five(cards("2h 2d 2c As Ah"))


def test_full_house_with_same_trips_is_decided_by_pair() -> None:
    # Possible with 7 cards when the trips are on the board.
    assert evaluate(cards("Kh Kd Kc 7s 2h Ah Ad")) > evaluate(cards("Kh Kd Kc 7s 2h Qh Qd"))


def test_pair_is_decided_by_kickers_in_order() -> None:
    assert evaluate_five(cards("Th Td Ac 8s 3h")) > evaluate_five(cards("Tc Ts Ad 7s 6h"))


def test_two_pair_is_decided_by_kicker() -> None:
    assert evaluate_five(cards("Jh Jd 4c 4s Kh")) > evaluate_five(cards("Jc Js 4d 4h Qh"))


def test_flush_compares_all_five_cards() -> None:
    assert evaluate_five(cards("Ah Qh 9h 6h 3h")) > evaluate_five(cards("As Qs 9s 6s 2s"))


def test_suits_never_break_ties() -> None:
    assert evaluate_five(cards("Ah Kd 9c 6s 3h")) == evaluate_five(cards("As Kc 9d 6h 3s"))


# --- Best 5 of 7 ----------------------------------------------------------------


def test_two_trips_make_a_full_house() -> None:
    assert evaluate(cards("9h 9d 9c 4s 4h 4d 2c")) == HandRank(
        HandCategory.FULL_HOUSE, ranks("94")
    )


def test_three_pairs_keep_the_best_two_and_best_kicker() -> None:
    # Pairs K, 8, 5 and a 3: the third pair's 5 is the kicker.
    assert evaluate(cards("Kh Kd 8c 8s 5h 5d 3c")) == HandRank(
        HandCategory.TWO_PAIR, ranks("K85")
    )


def test_six_suited_cards_keep_the_five_best() -> None:
    assert evaluate(cards("Ah Kh 9h 7h 4h 2h Qd")) == HandRank(
        HandCategory.FLUSH, ranks("AK974")
    )


def test_six_card_run_keeps_the_highest_straight() -> None:
    assert evaluate(cards("4h 5d 6c 7s 8h 9d Kc")) == HandRank(HandCategory.STRAIGHT, ranks("9"))


def test_wheel_with_a_six_plays_the_six_high_straight() -> None:
    assert evaluate(cards("Ah 2d 3c 4s 5h 6d Kc")) == HandRank(HandCategory.STRAIGHT, ranks("6"))


def test_straight_and_flush_without_straight_flush_is_a_flush() -> None:
    # Straight 5-9 and five hearts, but the hearts are not consecutive.
    assert evaluate(cards("5h 6h 7d 8h 9c Kh 2h")) == HandRank(
        HandCategory.FLUSH, ranks("K8652")
    )


def test_quads_take_the_best_remaining_kicker() -> None:
    assert evaluate(cards("7h 7d 7c 7s 2h Qd Jc")) == HandRank(
        HandCategory.FOUR_OF_A_KIND, ranks("7Q")
    )


def test_quads_beat_a_full_house_present_in_the_same_cards() -> None:
    assert evaluate(cards("7h 7d 7c 7s Kh Kd 2c")).category == HandCategory.FOUR_OF_A_KIND


def test_evaluate_accepts_five_and_six_cards() -> None:
    assert evaluate(cards("Ah Jd 9c 6s 3h")) == evaluate_five(cards("Ah Jd 9c 6s 3h"))
    assert evaluate(cards("Ah Jd 9c 6s 3h 3d")).category == HandCategory.PAIR


def test_evaluate_does_not_depend_on_card_order() -> None:
    hand = cards("Kh Kd 8c 8s 5h 5d 3c")
    assert evaluate(hand) == evaluate(list(reversed(hand)))


# --- compare(hand_a, hand_b, board) ----------------------------------------------


def test_compare_hand_a_wins() -> None:
    # Flush (A-high) against a pair of tens.
    assert compare(cards("As Ks"), cards("Th Td"), cards("Qs Js 2d 7c 3s")) == 1


def test_compare_hand_a_loses() -> None:
    assert compare(cards("Th Td"), cards("As Ks"), cards("Qs Js 2d 7c 3s")) == -1


def test_compare_board_plays_is_a_tie() -> None:
    # Broadway straight on the board: nobody can improve it.
    assert compare(cards("2c 3d"), cards("4h 5s"), cards("Ah Kd Qc Js Th")) == 0


def test_compare_same_kickers_is_a_tie() -> None:
    # Both play A-K with the board's Q-J-9: the 8 and 7 do not count.
    assert compare(cards("Ah 8c"), cards("Ad 7s"), cards("Kh Qd Jc 9s 2h")) == 0


def test_compare_kicker_decides() -> None:
    assert compare(cards("Ah Qc"), cards("Ad Js"), cards("As Kh 8d 5c 2h")) == 1


# --- Invalid input -------------------------------------------------------------


@pytest.mark.parametrize("hand", ["Ah Kd Qc Js", "Ah Kd Qc Js Th 9h 8h 7h"])
def test_evaluate_rejects_wrong_card_count(hand: str) -> None:
    with pytest.raises(ValueError):
        evaluate(cards(hand))


@pytest.mark.parametrize("hand", ["Ah Kd Qc Js", "Ah Kd Qc Js Th 9h"])
def test_evaluate_five_requires_exactly_five_cards(hand: str) -> None:
    with pytest.raises(ValueError):
        evaluate_five(cards(hand))


def test_evaluate_rejects_duplicate_cards() -> None:
    with pytest.raises(ValueError):
        evaluate(cards("Ah Ah Qc Js Th 2c"))


@pytest.mark.parametrize("card", [-1, 52])
def test_evaluate_rejects_invalid_card_ids(card: int) -> None:
    with pytest.raises(ValueError):
        evaluate([*cards("Ah Kd Qc Js"), card])


def test_compare_rejects_overlapping_hands() -> None:
    with pytest.raises(ValueError):
        compare(cards("Ah Kd"), cards("Ah Qs"), cards("2c 3d 4h 5s 7c"))


def test_compare_rejects_hand_sharing_a_board_card() -> None:
    with pytest.raises(ValueError):
        compare(cards("Ah Kd"), cards("Qh Qs"), cards("Ah 3d 4h 5s 7c"))


def test_compare_requires_two_hole_cards_and_five_board_cards() -> None:
    with pytest.raises(ValueError):
        compare(cards("Ah"), cards("Qh Qs"), cards("2c 3d 4h 5s 7c"))
    with pytest.raises(ValueError):
        compare(cards("Ah Kd"), cards("Qh Qs"), cards("2c 3d 4h 5s"))


# --- Exhaustive check against published combinatorics --------------------------

# Source: https://en.wikipedia.org/wiki/Poker_probability (5-card hands).
EXPECTED_CATEGORY_COUNTS = {
    HandCategory.STRAIGHT_FLUSH: 40,
    HandCategory.FOUR_OF_A_KIND: 624,
    HandCategory.FULL_HOUSE: 3_744,
    HandCategory.FLUSH: 5_108,
    HandCategory.STRAIGHT: 10_200,
    HandCategory.THREE_OF_A_KIND: 54_912,
    HandCategory.TWO_PAIR: 123_552,
    HandCategory.PAIR: 1_098_240,
    HandCategory.HIGH_CARD: 1_302_540,
}


@pytest.mark.slow
def test_all_five_card_hands_match_published_counts() -> None:
    category_counts: Counter[HandCategory] = Counter()
    distinct_ranks: set[HandRank] = set()
    for hand in combinations(range(52), 5):
        rank = evaluate_five(hand)
        category_counts[rank.category] += 1
        distinct_ranks.add(rank)
    assert category_counts == EXPECTED_CATEGORY_COUNTS
    assert sum(category_counts.values()) == 2_598_960
    assert len(distinct_ranks) == 7_462
