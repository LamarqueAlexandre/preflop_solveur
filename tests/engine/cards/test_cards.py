"""Tests for single-card encoding (0..51) and its text notation."""

import pytest

from engine.cards import (
    N_CARDS,
    card_rank,
    card_suit,
    format_card,
    make_card,
    parse_card,
)


def test_deck_has_52_distinct_cards() -> None:
    cards = {make_card(rank, suit) for rank in range(13) for suit in range(4)}
    assert N_CARDS == 52
    assert cards == set(range(52))


def test_card_encoding_is_4_rank_plus_suit() -> None:
    # Ranks: 2=0 .. A=12 ; suits: c=0, d=1, h=2, s=3.
    assert make_card(12, 3) == 51  # As
    assert make_card(0, 0) == 0  # 2c
    assert card_rank(51) == 12
    assert card_suit(51) == 3


@pytest.mark.parametrize(
    ("text", "rank", "suit"),
    [("As", 12, 3), ("Ah", 12, 2), ("Td", 8, 1), ("2c", 0, 0), ("Kh", 11, 2)],
)
def test_parse_card_known_values(text: str, rank: int, suit: int) -> None:
    card = parse_card(text)
    assert card_rank(card) == rank
    assert card_suit(card) == suit


def test_parse_format_roundtrip_for_all_cards() -> None:
    for card in range(N_CARDS):
        assert parse_card(format_card(card)) == card


@pytest.mark.parametrize("text", ["1h", "Ax", "A", "", "Ahh", "ah", "AH", "10h"])
def test_parse_card_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        parse_card(text)


@pytest.mark.parametrize("card", [-1, 52, 100])
def test_format_card_rejects_out_of_range(card: int) -> None:
    with pytest.raises(ValueError):
        format_card(card)
