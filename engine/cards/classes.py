"""The 169 preflop hand classes and their 13x13 grid layout.

A class index is its row-major grid position: ``index = row * 13 + col``.
Rows and columns run from A (0) down to 2 (12). Pairs sit on the diagonal,
suited hands above it (``col > row``), offsuit hands below it.
"""

from enum import Enum
from typing import Final

import numpy as np
import numpy.typing as npt

from engine.cards.cards import N_RANKS, RANK_CHARS, card_rank, card_suit
from engine.cards.combos import COMBOS

N_CLASSES: Final = N_RANKS * N_RANKS


class HandKind(Enum):
    """Pair, suited or offsuit."""

    PAIR = "pair"
    SUITED = "suited"
    OFFSUIT = "offsuit"


def _row(rank: int) -> int:
    """Grid row/column of a rank: A (12) -> 0, 2 (0) -> 12."""
    return N_RANKS - 1 - rank


def _rank_of_row(row: int) -> int:
    """Inverse of ``_row``."""
    return N_RANKS - 1 - row


def _check_class(index: int) -> None:
    if not 0 <= index < N_CLASSES:
        raise ValueError(f"invalid class index: {index}")


def grid_position(index: int) -> tuple[int, int]:
    """``(row, col)`` of a class in the 13x13 grid."""
    _check_class(index)
    return divmod(index, N_RANKS)


def class_kind(index: int) -> HandKind:
    """Whether a class is a pair, a suited or an offsuit hand."""
    row, col = grid_position(index)
    if row == col:
        return HandKind.PAIR
    return HandKind.SUITED if col > row else HandKind.OFFSUIT


def class_of_cards(card_a: int, card_b: int) -> int:
    """Class index of two distinct cards, in any order."""
    if card_a == card_b:
        raise ValueError(f"same card twice: {card_a}")
    high_row = _row(max(card_rank(card_a), card_rank(card_b)))
    low_row = _row(min(card_rank(card_a), card_rank(card_b)))
    if card_suit(card_a) == card_suit(card_b):
        return high_row * N_RANKS + low_row  # above the diagonal
    return low_row * N_RANKS + high_row  # below it (or on it for pairs)


def format_class(index: int) -> str:
    """Notation of a class: ``"AA"``, ``"AKs"``, ``"T9o"``."""
    row, col = grid_position(index)
    high = RANK_CHARS[_rank_of_row(min(row, col))]
    low = RANK_CHARS[_rank_of_row(max(row, col))]
    if row == col:
        return high + low
    return high + low + ("s" if col > row else "o")


def parse_class(text: str) -> int:
    """Parse a class such as ``"AA"``, ``"AKs"`` or ``"T9o"`` (high rank first)."""
    if len(text) not in (2, 3) or text[0] not in RANK_CHARS or text[1] not in RANK_CHARS:
        raise ValueError(f"invalid hand class: {text!r}")
    high, low = RANK_CHARS.index(text[0]), RANK_CHARS.index(text[1])
    suffix = text[2:]
    if high == low and suffix == "":
        return _row(high) * N_RANKS + _row(high)
    if high > low and suffix == "s":
        return _row(high) * N_RANKS + _row(low)
    if high > low and suffix == "o":
        return _row(low) * N_RANKS + _row(high)
    raise ValueError(f"invalid hand class: {text!r}")


def _build_class_of_combo() -> npt.NDArray[np.int16]:
    table = np.array([class_of_cards(int(a), int(b)) for a, b in COMBOS], dtype=np.int16)
    table.setflags(write=False)
    return table


CLASS_OF_COMBO: Final = _build_class_of_combo()
"""Read-only array (1326,): class index of each combo."""


def _build_weights() -> npt.NDArray[np.int64]:
    table = np.bincount(CLASS_OF_COMBO, minlength=N_CLASSES).astype(np.int64)
    table.setflags(write=False)
    return table


CLASS_WEIGHTS: Final = _build_weights()
"""Read-only array (169,): number of combos per class (6 pair, 4 suited, 12 offsuit)."""


def _build_combos_of_class() -> tuple[npt.NDArray[np.int16], ...]:
    order = np.argsort(CLASS_OF_COMBO, kind="stable").astype(np.int16)
    groups = np.split(order, np.cumsum(CLASS_WEIGHTS)[:-1])
    for group in groups:
        group.setflags(write=False)
    return tuple(groups)


_COMBOS_OF_CLASS: Final = _build_combos_of_class()


def combos_of_class(index: int) -> npt.NDArray[np.int16]:
    """Read-only array of the combo indices belonging to a class."""
    _check_class(index)
    return _COMBOS_OF_CLASS[index]
