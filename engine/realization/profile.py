"""Equity realization profiles (FR-007, FR-008, D-002, D-012).

A profile gives a realization factor R for each flop context: number of
players at the flop, pot type, stack tranche and position at the flop. At the
flop, player i gets the share ``R_i * eq_i / sum_j R_j * eq_j`` of the pot
(D-002), so only the ratios between factors matter.

Profiles are versioned JSON files. An entry may carry an optional
``hand_category`` (V2): it refines the base entry of the same context and is
loaded and validated, but the MVP always uses the base factor (FR-008).
"""

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from importlib import resources
from itertools import product
from pathlib import Path
from types import MappingProxyType
from typing import Final

from engine.game.config import Tranche
from engine.game.tree import Position

FORMAT_VERSION: Final = 1
"""Version of the profile file format understood by this engine."""

_TOP_LEVEL_KEYS: Final = frozenset({"format_version", "name", "version", "description", "entries"})
_ENTRY_KEYS: Final = frozenset({"players", "pot_type", "tranche", "position", "factor"})
_OPTIONAL_ENTRY_KEYS: Final = frozenset({"hand_category"})

_FLOP_ORDER: Final = (Position.SB, Position.BB, Position.BTN)
"""Order of action after the flop: first to act first."""


class ProfileError(ValueError):
    """An invalid or unreadable realization profile."""


class PotType(Enum):
    """Preflop history of a pot that reaches the flop."""

    LIMPED = "limped"
    RAISED = "raised"  # a single raise, isolation included
    THREE_BET = "3bet"


class FlopPosition(Enum):
    """Position at the flop: IP/OOP heads-up, order of action three-way."""

    IP = "ip"
    OOP = "oop"
    FIRST = "first"
    MIDDLE = "middle"
    LAST = "last"


_POSITIONS_BY_PLAYERS: Final[Mapping[int, tuple[FlopPosition, ...]]] = MappingProxyType(
    {
        2: (FlopPosition.OOP, FlopPosition.IP),
        3: (FlopPosition.FIRST, FlopPosition.MIDDLE, FlopPosition.LAST),
    }
)
"""Flop positions for each player count, in order of action."""


@dataclass(frozen=True)
class RealizationKey:
    """Context of a flop pot (FR-007)."""

    players: int
    pot_type: PotType
    tranche: Tranche
    position: FlopPosition

    def __post_init__(self) -> None:
        if self.players not in _POSITIONS_BY_PLAYERS:
            raise ValueError(f"players at the flop must be 2 or 3, got {self.players}")
        if self.position not in _POSITIONS_BY_PLAYERS[self.players]:
            raise ValueError(
                f"position {self.position.value!r} does not exist with {self.players} players"
            )


def all_keys() -> tuple[RealizationKey, ...]:
    """Every context a profile must cover: 18 heads-up and 27 three-way."""
    return tuple(
        RealizationKey(players, pot_type, tranche, position)
        for players, positions in _POSITIONS_BY_PLAYERS.items()
        for pot_type, tranche, position in product(PotType, Tranche, positions)
    )


@dataclass(frozen=True)
class RealizationProfile:
    """A named, versioned set of realization factors."""

    name: str
    version: str
    description: str
    factors: Mapping[RealizationKey, float] = field(repr=False)
    category_factors: Mapping[tuple[RealizationKey, str], float] = field(repr=False)

    def factor(self, key: RealizationKey) -> float:
        """Realization factor of a context (one factor for every hand at the MVP)."""
        return self.factors[key]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileError(message)


def _enum_value[E: Enum](enum: type[E], value: object, label: str) -> E:
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(repr(member.value) for member in enum)
        raise ProfileError(f"unknown {label} {value!r}, expected one of {allowed}") from None


def _parse_entry(entry: object, index: int) -> tuple[RealizationKey, str | None, float]:
    where = f"entry {index}"
    _require(isinstance(entry, dict), f"{where}: must be an object")
    assert isinstance(entry, dict)
    keys = set(entry)
    _require(keys >= _ENTRY_KEYS, f"{where}: missing {sorted(_ENTRY_KEYS - keys)}")
    unknown = keys - _ENTRY_KEYS - _OPTIONAL_ENTRY_KEYS
    _require(not unknown, f"{where}: unknown keys {sorted(unknown)}")

    players = entry["players"]
    _require(type(players) is int, f"{where}: players must be an integer")
    try:
        key = RealizationKey(
            players=players,
            pot_type=_enum_value(PotType, entry["pot_type"], "pot type"),
            tranche=_enum_value(Tranche, entry["tranche"], "tranche"),
            position=_enum_value(FlopPosition, entry["position"], "position"),
        )
    except ValueError as error:  # ProfileError included
        raise ProfileError(f"{where}: {error}") from None

    factor = entry["factor"]
    _require(
        isinstance(factor, int | float) and not isinstance(factor, bool),
        f"{where}: factor must be a number",
    )
    _require(math.isfinite(factor) and factor > 0, f"{where}: factor must be > 0, got {factor}")

    category = entry.get("hand_category")
    _require(
        category is None or (isinstance(category, str) and category != ""),
        f"{where}: hand_category must be a non-empty string",
    )
    return key, category, float(factor)


def parse_profile(data: object) -> RealizationProfile:
    """Validate the decoded JSON of a profile and build it."""
    _require(isinstance(data, dict), "a profile must be a JSON object")
    assert isinstance(data, dict)
    keys = set(data)
    _require(keys >= _TOP_LEVEL_KEYS, f"missing keys {sorted(_TOP_LEVEL_KEYS - keys)}")
    _require(keys <= _TOP_LEVEL_KEYS, f"unknown keys {sorted(keys - _TOP_LEVEL_KEYS)}")
    _require(
        data["format_version"] == FORMAT_VERSION,
        f"unsupported format_version {data['format_version']!r}, expected {FORMAT_VERSION}",
    )
    for label in ("name", "version", "description"):
        _require(isinstance(data[label], str), f"{label} must be a string")
    _require(bool(data["name"]) and bool(data["version"]), "name and version must not be empty")
    _require(isinstance(data["entries"], list), "entries must be a list")

    factors: dict[RealizationKey, float] = {}
    category_factors: dict[tuple[RealizationKey, str], float] = {}
    for index, entry in enumerate(data["entries"]):
        key, category, factor = _parse_entry(entry, index)
        if category is None:
            _require(key not in factors, f"entry {index}: duplicate context {key}")
            factors[key] = factor
        else:
            _require(
                (key, category) not in category_factors,
                f"entry {index}: duplicate context {key} for category {category!r}",
            )
            category_factors[(key, category)] = factor

    missing = [key for key in all_keys() if key not in factors]
    # The base grid is complete, so every hand_category entry refines a base entry.
    _require(not missing, f"{len(missing)} contexts without a factor, e.g. {missing[:3]}")

    return RealizationProfile(
        name=data["name"],
        version=data["version"],
        description=data["description"],
        factors=MappingProxyType(factors),
        category_factors=MappingProxyType(category_factors),
    )


def load_profile(path: Path) -> RealizationProfile:
    """Read and validate a profile file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError(f"cannot read profile {path}: {error}") from error
    return parse_profile(data)


def builtin_profile(name: str) -> RealizationProfile:
    """A profile shipped with the engine, by name (e.g. ``"default"``)."""
    source = resources.files("engine.realization").joinpath("profiles", f"{name}.json")
    if not source.is_file():
        raise ProfileError(f"no built-in realization profile named {name!r}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProfileError(f"cannot read built-in profile {name!r}: {error}") from error
    return parse_profile(data)


def default_profile() -> RealizationProfile:
    """The default profile (D-012)."""
    return builtin_profile("default")


def pot_type_of(raise_level: int) -> PotType:
    """Pot type of a flop pot from the preflop raise level of its node.

    Level 3 (4-bet) never reaches the flop: a 4-bet is always all-in, and with
    equal stacks everyone left is then all-in (D-005).
    """
    types = {0: PotType.LIMPED, 1: PotType.RAISED, 2: PotType.THREE_BET}
    if raise_level not in types:
        raise ValueError(f"no flop pot type for raise level {raise_level}")
    return types[raise_level]


def flop_positions(seats: Iterable[Position]) -> dict[Position, FlopPosition]:
    """Position at the flop of each seat still in the hand (order: SB, BB, BTN)."""
    in_hand = set(seats)
    ordered = [seat for seat in _FLOP_ORDER if seat in in_hand]
    if len(ordered) not in _POSITIONS_BY_PLAYERS:
        raise ValueError(f"a flop needs 2 or 3 players, got {sorted(in_hand)}")
    return dict(zip(ordered, _POSITIONS_BY_PLAYERS[len(ordered)], strict=True))
