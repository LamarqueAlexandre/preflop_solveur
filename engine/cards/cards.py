"""Single cards encoded as integers 0..51: ``card = 4 * rank + suit``.

Ranks go from 2 (0) to A (12); suits are c=0, d=1, h=2, s=3.
"""

from typing import Final

RANK_CHARS: Final = "23456789TJQKA"
SUIT_CHARS: Final = "cdhs"
N_RANKS: Final = 13
N_SUITS: Final = 4
N_CARDS: Final = 52


def make_card(rank: int, suit: int) -> int:
    """Return the card id for ``rank`` (0=2 .. 12=A) and ``suit`` (0..3)."""
    if not (0 <= rank < N_RANKS and 0 <= suit < N_SUITS):
        raise ValueError(f"invalid rank/suit: {rank}/{suit}")
    return N_SUITS * rank + suit


def card_rank(card: int) -> int:
    """Rank of a card, 0 (deuce) to 12 (ace)."""
    return card // N_SUITS


def card_suit(card: int) -> int:
    """Suit of a card, 0..3 (c, d, h, s)."""
    return card % N_SUITS


def parse_card(text: str) -> int:
    """Parse a card such as ``"Ah"`` or ``"Td"``."""
    if len(text) != 2 or text[0] not in RANK_CHARS or text[1] not in SUIT_CHARS:
        raise ValueError(f"invalid card: {text!r}")
    return make_card(RANK_CHARS.index(text[0]), SUIT_CHARS.index(text[1]))


def format_card(card: int) -> str:
    """Format a card id as text, e.g. ``51 -> "As"``."""
    if not 0 <= card < N_CARDS:
        raise ValueError(f"invalid card id: {card}")
    return RANK_CHARS[card_rank(card)] + SUIT_CHARS[card_suit(card)]
