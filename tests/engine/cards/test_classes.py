"""Tests for the 169 hand classes, their combo weights and the 13x13 grid indexing."""

import numpy as np
import pytest

from engine.cards import (
    CLASS_OF_COMBO,
    CLASS_WEIGHTS,
    COMBOS,
    N_CLASSES,
    N_COMBOS,
    HandKind,
    class_kind,
    class_of_cards,
    combo_index,
    combos_of_class,
    format_class,
    grid_position,
    parse_card,
    parse_class,
)


def cls(text: str) -> int:
    return parse_class(text)


def cards_class(a: str, b: str) -> int:
    return class_of_cards(parse_card(a), parse_card(b))


# --- Counting --------------------------------------------------------------------


def test_there_are_169_classes_13_pairs_78_suited_78_offsuit() -> None:
    kinds = [class_kind(c) for c in range(N_CLASSES)]
    assert N_CLASSES == 169
    assert kinds.count(HandKind.PAIR) == 13
    assert kinds.count(HandKind.SUITED) == 78
    assert kinds.count(HandKind.OFFSUIT) == 78


def test_weights_are_6_4_12_by_kind() -> None:
    expected = {HandKind.PAIR: 6, HandKind.SUITED: 4, HandKind.OFFSUIT: 12}
    for c in range(N_CLASSES):
        assert CLASS_WEIGHTS[c] == expected[class_kind(c)]


def test_weights_sum_to_1326() -> None:
    assert int(CLASS_WEIGHTS.sum()) == N_COMBOS


def test_every_combo_belongs_to_exactly_one_class_consistent_with_weights() -> None:
    assert CLASS_OF_COMBO.shape == (N_COMBOS,)
    counts = np.bincount(CLASS_OF_COMBO, minlength=N_CLASSES)
    assert np.array_equal(counts, CLASS_WEIGHTS)


def test_lookup_tables_are_read_only() -> None:
    with pytest.raises(ValueError):
        CLASS_OF_COMBO[0] = 1
    with pytest.raises(ValueError):
        CLASS_WEIGHTS[0] = 1


# --- Hand-written cases --------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Ah", "As", "AA"),
        ("2c", "2d", "22"),
        ("Ah", "Kh", "AKs"),
        ("Ah", "Kd", "AKo"),
        ("Kd", "Ah", "AKo"),
        ("9s", "Ts", "T9s"),
        ("3c", "2d", "32o"),
    ],
)
def test_class_of_cards_hand_written(a: str, b: str, expected: str) -> None:
    assert cards_class(a, b) == cls(expected)


def test_class_of_combo_table_matches_class_of_cards() -> None:
    for i, (a, b) in enumerate(COMBOS):
        assert CLASS_OF_COMBO[i] == class_of_cards(int(a), int(b))


def test_combos_of_aks_are_the_four_suited_ak() -> None:
    combos = combos_of_class(cls("AKs"))
    assert len(combos) == 4
    expected = {combo_index(parse_card("A" + s), parse_card("K" + s)) for s in "cdhs"}
    assert {int(i) for i in combos} == expected


def test_combos_of_class_matches_lookup_table() -> None:
    for c in range(N_CLASSES):
        combos = combos_of_class(c)
        assert len(combos) == CLASS_WEIGHTS[c]
        assert all(CLASS_OF_COMBO[i] == c for i in combos)


def test_class_of_cards_rejects_same_card() -> None:
    with pytest.raises(ValueError):
        class_of_cards(5, 5)


# --- 13x13 grid ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "row", "col"),
    [
        ("AA", 0, 0),
        ("AKs", 0, 1),
        ("AKo", 1, 0),
        ("KK", 1, 1),
        ("A2s", 0, 12),
        ("A2o", 12, 0),
        ("22", 12, 12),
        ("32s", 11, 12),
        ("32o", 12, 11),
    ],
)
def test_grid_positions(text: str, row: int, col: int) -> None:
    assert grid_position(cls(text)) == (row, col)


def test_class_index_is_row_major_grid_position() -> None:
    for c in range(N_CLASSES):
        row, col = grid_position(c)
        assert c == row * 13 + col


def test_grid_layout_pairs_diagonal_suited_above_offsuit_below() -> None:
    for c in range(N_CLASSES):
        row, col = grid_position(c)
        kind = class_kind(c)
        if row == col:
            assert kind is HandKind.PAIR
        elif col > row:
            assert kind is HandKind.SUITED
        else:
            assert kind is HandKind.OFFSUIT


# --- Notation ------------------------------------------------------------------


def test_class_notation_roundtrip() -> None:
    for c in range(N_CLASSES):
        assert parse_class(format_class(c)) == c


@pytest.mark.parametrize("text", ["AKx", "KAs", "AK", "AAs", "AAo", "A", "", "akS", "1Ks"])
def test_parse_class_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        parse_class(text)


@pytest.mark.parametrize("c", [-1, 169])
def test_class_functions_reject_out_of_range(c: int) -> None:
    with pytest.raises(ValueError):
        format_class(c)
    with pytest.raises(ValueError):
        grid_position(c)
