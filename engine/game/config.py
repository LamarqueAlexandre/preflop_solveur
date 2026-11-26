"""Immutable game configuration: stacks, blinds, sizings by stack tranche (FR-001 to FR-004).

All amounts are in big blinds. Raise sizes are "raise to" totals (D-011): an
open to 2bb puts 2bb in front of the raiser, big blind included.
"""

from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise
from typing import Final, Self

SHORT_MAX: Final = 8.0
"""Largest stack (bb) of the short tranche."""
MEDIUM_MAX: Final = 15.0
"""Largest stack (bb) of the medium tranche."""
MIN_RAISE_TO: Final = 2.0
"""Smallest legal open raise, in big blinds (a min-raise)."""

STACK_GRID: Final = tuple(float(stack) for stack in range(3, 26))
"""Equal starting stacks solved at the MVP: 3 to 25bb by 1bb (FR-003)."""


class Tranche(Enum):
    """Stack depth tranche selecting the available sizings (FR-004)."""

    SHORT = "short"  # <= 8bb
    MEDIUM = "medium"  # 9 to 15bb
    DEEP = "deep"  # > 15bb


def tranche_of(stack: float) -> Tranche:
    """Tranche of a stack depth in big blinds."""
    if stack <= 0:
        raise ValueError(f"stack must be positive, got {stack}")
    if stack <= SHORT_MAX:
        return Tranche.SHORT
    if stack <= MEDIUM_MAX:
        return Tranche.MEDIUM
    return Tranche.DEEP


def _check_increasing(values: tuple[float, ...], minimum: float, label: str) -> None:
    if any(value < minimum for value in values):
        raise ValueError(f"{label} must be at least {minimum}, got {values}")
    if any(b <= a for a, b in pairwise(values)):
        raise ValueError(f"{label} must be strictly increasing, got {values}")


@dataclass(frozen=True)
class TrancheSizings:
    """Sized raises of one tranche, besides fold, limp/call and all-in (always available).

    - ``open_raises``: open raise-to amounts (bb), e.g. (2.0, 2.5).
    - ``three_bet_multipliers``: 3-bet to this multiple of the raise faced.
    - ``isolation_base``: raise-to over one limper; None means all-in only.
    - ``isolation_per_extra_limper``: added for each further limper.
    """

    open_raises: tuple[float, ...] = ()
    three_bet_multipliers: tuple[float, ...] = ()
    isolation_base: float | None = None
    isolation_per_extra_limper: float = 1.0

    def __post_init__(self) -> None:
        _check_increasing(self.open_raises, MIN_RAISE_TO, "open raises")
        _check_increasing(self.three_bet_multipliers, 2.0, "3-bet multipliers")
        if self.isolation_base is not None and self.isolation_base < MIN_RAISE_TO:
            raise ValueError(f"isolation raise must be at least {MIN_RAISE_TO}bb")
        if self.isolation_per_extra_limper < 0:
            raise ValueError("isolation increment per limper must not be negative")

    def three_bet_sizes(self, raise_to: float) -> tuple[float, ...]:
        """Sized 3-bets (raise-to amounts) facing a raise to ``raise_to``."""
        return tuple(multiplier * raise_to for multiplier in self.three_bet_multipliers)

    def isolation_size(self, n_limpers: int) -> float | None:
        """Isolation raise-to facing ``n_limpers`` limpers (SB complete included), or None."""
        if n_limpers < 1:
            raise ValueError(f"isolation needs at least one limper, got {n_limpers}")
        if self.isolation_base is None:
            return None
        return self.isolation_base + self.isolation_per_extra_limper * (n_limpers - 1)


@dataclass(frozen=True)
class SizingTable:
    """Sizings of the three tranches."""

    short: TrancheSizings
    medium: TrancheSizings
    deep: TrancheSizings

    def for_tranche(self, tranche: Tranche) -> TrancheSizings:
        return {Tranche.SHORT: self.short, Tranche.MEDIUM: self.medium, Tranche.DEEP: self.deep}[
            tranche
        ]


def default_sizing_table() -> SizingTable:
    """Sizings of FR-004, as interpreted by D-011."""
    return SizingTable(
        short=TrancheSizings(),
        medium=TrancheSizings(open_raises=(2.0,), isolation_base=3.0),
        deep=TrancheSizings(
            open_raises=(2.0, 2.5), three_bet_multipliers=(3.0,), isolation_base=3.0
        ),
    )


@dataclass(frozen=True)
class GameConfig:
    """Everything that defines a game, in big blinds; immutable and hashable.

    ``stacks`` are the starting stacks of BTN, SB and BB. The tranche follows
    the smallest stack (all stacks are equal at the MVP, FR-003).
    """

    stacks: tuple[float, float, float]
    small_blind: float = 0.5
    big_blind: float = 1.0
    sizing_table: SizingTable = field(default_factory=default_sizing_table)
    all_in_threshold: float = 1.0
    realization_profile: str = "default"

    def __post_init__(self) -> None:
        if not 0 < self.small_blind < self.big_blind:
            raise ValueError(
                f"blinds must satisfy 0 < small < big, got {self.small_blind}/{self.big_blind}"
            )
        if any(stack < self.big_blind for stack in self.stacks):
            raise ValueError(f"every stack must cover the big blind, got {self.stacks}")
        if self.all_in_threshold < 0:
            raise ValueError("all-in threshold must not be negative")

    @classmethod
    def equal_stacks(cls, stack: float, **kwargs: object) -> Self:
        """Configuration where BTN, SB and BB all start with ``stack``."""
        return cls(stacks=(stack, stack, stack), **kwargs)  # type: ignore[arg-type]

    @property
    def tranche(self) -> Tranche:
        return tranche_of(min(self.stacks))

    @property
    def sizings(self) -> TrancheSizings:
        return self.sizing_table.for_tranche(self.tranche)

    def raise_to(self, amount: float, stack: float) -> float:
        """Raise-to amount actually used by a player with ``stack``.

        Becomes all-in (the whole stack) when it would leave strictly less
        than ``all_in_threshold`` behind (D-011).
        """
        if amount <= 0:
            raise ValueError(f"raise amount must be positive, got {amount}")
        if stack - amount < self.all_in_threshold:
            return stack
        return amount


def default_configs() -> tuple[GameConfig, ...]:
    """The 23 default configurations of the stack grid (FR-003, FR-004)."""
    return tuple(GameConfig.equal_stacks(stack) for stack in STACK_GRID)
