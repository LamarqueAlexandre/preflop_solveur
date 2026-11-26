"""Main pot and side pots for n players.

Each distinct contribution level reached by a live player closes a pot. That
pot collects, from every player (folded ones included, as dead money), what
they put in between the previous level and this one; it can be won by the
live players who reached the level. Chips above the highest live level can
only come from folded players and are added to the last pot.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Pot:
    """A pot and the indices of the players who can win it."""

    amount: float
    eligible: frozenset[int]


def resolve_pots(contributions: Sequence[float], folded: Sequence[bool]) -> tuple[Pot, ...]:
    """Split the players' total contributions into the main pot then the side pots.

    ``contributions[i]`` is everything player i put in this hand (bb);
    ``folded[i]`` tells whether player i folded. Pots come from the main pot
    (open to every live player) to the last side pot; the last one may have a
    single eligible player (an uncalled excess, which goes back to that player).
    """
    if len(contributions) != len(folded):
        raise ValueError("contributions and folded must have the same length")
    if len(contributions) < 2:
        raise ValueError("at least two players are needed")
    if any(amount < 0 for amount in contributions):
        raise ValueError(f"contributions must not be negative, got {list(contributions)}")
    live = [i for i, has_folded in enumerate(folded) if not has_folded]
    if not live:
        raise ValueError("at least one player must still be in the hand")

    levels = sorted({contributions[i] for i in live})
    pots: list[Pot] = []
    previous = 0.0
    for level in levels:
        amount = sum(min(c, level) - min(c, previous) for c in contributions)
        eligible = frozenset(i for i in live if contributions[i] >= level)
        if amount > 0:
            pots.append(Pot(amount, eligible))
        previous = level

    dead_above = sum(max(c - previous, 0.0) for c in contributions)
    if dead_above > 0:
        if pots:
            last = pots[-1]
            pots[-1] = Pot(last.amount + dead_above, last.eligible)
        else:
            pots.append(Pot(dead_above, frozenset(live)))
    return tuple(pots)
