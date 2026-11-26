"""The 1326 two-card starting combos."""

from itertools import combinations
from typing import Final

import numpy as np
import numpy.typing as npt

from engine.cards.cards import N_CARDS

N_COMBOS: Final = N_CARDS * (N_CARDS - 1) // 2


def _build_combos() -> npt.NDArray[np.int8]:
    table = np.array(list(combinations(range(N_CARDS), 2)), dtype=np.int8)
    table.setflags(write=False)
    return table


COMBOS: Final = _build_combos()
"""Read-only array (1326, 2): each row holds two card ids, lower id first."""

_INDEX: Final = {(int(a), int(b)): i for i, (a, b) in enumerate(COMBOS)}


def combo_index(card_a: int, card_b: int) -> int:
    """Index (0..1325) of the combo made of two distinct cards, in any order."""
    low, high = min(card_a, card_b), max(card_a, card_b)
    try:
        return _INDEX[(low, high)]
    except KeyError:
        raise ValueError(f"invalid combo: {card_a}, {card_b}") from None
