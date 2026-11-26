"""Tests for the 1326 two-card combos."""

import pytest

from engine.cards import COMBOS, N_COMBOS, combo_index, parse_card


def test_there_are_1326_combos() -> None:
    assert N_COMBOS == 1326 == 52 * 51 // 2
    assert COMBOS.shape == (1326, 2)


def test_combos_are_distinct_and_have_two_different_cards() -> None:
    pairs = {(int(a), int(b)) for a, b in COMBOS}
    assert len(pairs) == 1326
    assert all(a < b for a, b in pairs)
    assert all(0 <= a < 52 and 0 <= b < 52 for a, b in pairs)


def test_combo_table_is_read_only() -> None:
    with pytest.raises(ValueError):
        COMBOS[0, 0] = 5


def test_combo_index_inverts_the_table() -> None:
    for i, (a, b) in enumerate(COMBOS):
        assert combo_index(int(a), int(b)) == i


def test_combo_index_ignores_card_order() -> None:
    ah, kd = parse_card("Ah"), parse_card("Kd")
    assert combo_index(ah, kd) == combo_index(kd, ah)


@pytest.mark.parametrize(("a", "b"), [(5, 5), (-1, 3), (3, 52)])
def test_combo_index_rejects_invalid_cards(a: int, b: int) -> None:
    with pytest.raises(ValueError):
        combo_index(a, b)
