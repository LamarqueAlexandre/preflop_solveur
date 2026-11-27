"""Tests for equity realization profiles (FR-007, FR-008, D-002, D-012)."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from engine.game import Position, Tranche
from engine.realization import (
    FORMAT_VERSION,
    FlopPosition,
    PotType,
    ProfileError,
    RealizationKey,
    all_keys,
    builtin_profile,
    default_profile,
    flop_positions,
    load_profile,
    parse_profile,
    pot_type_of,
)

TRANCHES_SHORT_TO_DEEP = (Tranche.SHORT, Tranche.MEDIUM, Tranche.DEEP)


def _entry(key: RealizationKey, factor: float = 1.0) -> dict[str, Any]:
    return {
        "players": key.players,
        "pot_type": key.pot_type.value,
        "tranche": key.tranche.value,
        "position": key.position.value,
        "factor": factor,
    }


def _flat_profile_data() -> dict[str, Any]:
    """A valid profile where every factor is 1 (raw equity)."""
    return {
        "format_version": FORMAT_VERSION,
        "name": "flat",
        "version": "1.0.0",
        "description": "Every factor is 1.",
        "entries": [_entry(key) for key in all_keys()],
    }


# --- Keys ----------------------------------------------------------------------------


def test_grid_has_45_keys() -> None:
    keys = all_keys()
    assert len(keys) == 45
    assert len(set(keys)) == 45
    assert sum(key.players == 2 for key in keys) == 18
    assert sum(key.players == 3 for key in keys) == 27


@pytest.mark.parametrize(
    ("players", "position"),
    [
        (2, FlopPosition.FIRST),
        (2, FlopPosition.MIDDLE),
        (2, FlopPosition.LAST),
        (3, FlopPosition.IP),
        (3, FlopPosition.OOP),
    ],
)
def test_key_rejects_position_of_the_wrong_player_count(
    players: int, position: FlopPosition
) -> None:
    with pytest.raises(ValueError, match="position"):
        RealizationKey(players, PotType.LIMPED, Tranche.SHORT, position)


def test_key_rejects_player_count() -> None:
    with pytest.raises(ValueError, match="players"):
        RealizationKey(4, PotType.LIMPED, Tranche.SHORT, FlopPosition.FIRST)


# --- Default profile -----------------------------------------------------------------


def test_default_profile_loads_complete_and_positive() -> None:
    profile = default_profile()
    assert profile.name == "default"
    assert profile.version
    for key in all_keys():
        assert profile.factor(key) > 0


def test_default_profile_is_the_builtin_named_default() -> None:
    assert builtin_profile("default") == default_profile()


def test_unknown_builtin_profile() -> None:
    with pytest.raises(ProfileError, match="nope"):
        builtin_profile("nope")


@pytest.mark.parametrize("players", [2, 3])
@pytest.mark.parametrize("pot_type", list(PotType))
def test_default_factors_get_closer_to_one_as_the_tranche_gets_shorter(
    players: int, pot_type: PotType
) -> None:
    """FR-008: the shorter the tranche, the closer the factors are to 1."""
    profile = default_profile()
    positions = {key.position for key in all_keys() if key.players == players}
    for position in positions:
        distances = [
            abs(profile.factor(RealizationKey(players, pot_type, tranche, position)) - 1.0)
            for tranche in TRANCHES_SHORT_TO_DEEP
        ]
        assert distances == sorted(distances), (players, pot_type, position, distances)


@pytest.mark.parametrize("tranche", list(Tranche))
@pytest.mark.parametrize("pot_type", list(PotType))
def test_default_factors_favour_position(tranche: Tranche, pot_type: PotType) -> None:
    profile = default_profile()

    def factor(players: int, position: FlopPosition) -> float:
        return profile.factor(RealizationKey(players, pot_type, tranche, position))

    assert factor(2, FlopPosition.IP) >= factor(2, FlopPosition.OOP)
    assert (
        factor(3, FlopPosition.LAST)
        >= factor(3, FlopPosition.MIDDLE)
        >= factor(3, FlopPosition.FIRST)
    )


# --- Loading -------------------------------------------------------------------------


def test_parse_flat_profile() -> None:
    profile = parse_profile(_flat_profile_data())
    assert profile.name == "flat"
    assert profile.version == "1.0.0"
    assert all(profile.factor(key) == 1.0 for key in all_keys())


def test_load_profile_from_file(tmp_path: Path) -> None:
    path = tmp_path / "flat.json"
    path.write_text(json.dumps(_flat_profile_data()), encoding="utf-8")
    assert load_profile(path) == parse_profile(_flat_profile_data())


def test_load_profile_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile(path)


def test_profile_with_hand_category_loads() -> None:
    """V2 extension: category entries refine a base entry; the MVP uses the base factor."""
    data = _flat_profile_data()
    key = RealizationKey(2, PotType.RAISED, Tranche.DEEP, FlopPosition.IP)
    data["entries"].append(_entry(key, 1.2) | {"hand_category": "suited_connectors"})
    profile = parse_profile(data)
    assert profile.factor(key) == 1.0
    assert profile.category_factors == {(key, "suited_connectors"): 1.2}


def test_profile_without_hand_category_has_no_category_factors() -> None:
    assert parse_profile(_flat_profile_data()).category_factors == {}


def _invalid(mutate: Any) -> dict[str, Any]:
    data = copy.deepcopy(_flat_profile_data())
    mutate(data)
    return data


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(_invalid(lambda d: d["entries"].pop()), id="missing entry"),
        pytest.param(
            _invalid(lambda d: d["entries"].append(dict(d["entries"][0]))), id="duplicate"
        ),
        pytest.param(_invalid(lambda d: d["entries"][0].update(factor=0.0)), id="zero factor"),
        pytest.param(_invalid(lambda d: d["entries"][0].update(factor=-1.0)), id="negative factor"),
        pytest.param(
            _invalid(lambda d: d["entries"][0].update(factor="1.0")), id="factor not a number"
        ),
        pytest.param(
            _invalid(lambda d: d["entries"][0].update(pot_type="4bet")), id="unknown pot type"
        ),
        pytest.param(
            _invalid(lambda d: d["entries"][0].update(tranche="huge")), id="unknown tranche"
        ),
        pytest.param(
            _invalid(lambda d: d["entries"][0].update(players=2, position="first")),
            id="position of the wrong player count",
        ),
        pytest.param(_invalid(lambda d: d["entries"][0].update(factr=1.0)), id="unknown entry key"),
        pytest.param(_invalid(lambda d: d.update(extra=1)), id="unknown top-level key"),
        pytest.param(_invalid(lambda d: d.pop("name")), id="missing name"),
        pytest.param(_invalid(lambda d: d.update(format_version=99)), id="unknown format"),
        pytest.param(
            _invalid(
                lambda d: d["entries"].append(d["entries"].pop(0) | {"hand_category": "pairs"})
            ),
            id="category entry without base entry",
        ),
    ],
)
def test_invalid_profiles_are_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ProfileError):
        parse_profile(data)


def test_profile_error_is_a_value_error() -> None:
    assert issubclass(ProfileError, ValueError)


# --- Context of a flop pot -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raise_level", "expected"),
    [(0, PotType.LIMPED), (1, PotType.RAISED), (2, PotType.THREE_BET)],
)
def test_pot_type_of(raise_level: int, expected: PotType) -> None:
    assert pot_type_of(raise_level) is expected


@pytest.mark.parametrize("raise_level", [-1, 3])
def test_pot_type_of_rejects_levels_without_flop(raise_level: int) -> None:
    """A 4-bet is always all-in: no 4-bet pot reaches the flop at the MVP."""
    with pytest.raises(ValueError):
        pot_type_of(raise_level)


@pytest.mark.parametrize(
    ("seats", "expected"),
    [
        (
            {Position.BTN, Position.SB},
            {Position.SB: FlopPosition.OOP, Position.BTN: FlopPosition.IP},
        ),
        (
            {Position.BTN, Position.BB},
            {Position.BB: FlopPosition.OOP, Position.BTN: FlopPosition.IP},
        ),
        (
            {Position.SB, Position.BB},
            {Position.SB: FlopPosition.OOP, Position.BB: FlopPosition.IP},
        ),
        (
            {Position.BTN, Position.SB, Position.BB},
            {
                Position.SB: FlopPosition.FIRST,
                Position.BB: FlopPosition.MIDDLE,
                Position.BTN: FlopPosition.LAST,
            },
        ),
    ],
)
def test_flop_positions(seats: set[Position], expected: dict[Position, FlopPosition]) -> None:
    assert flop_positions(seats) == expected


@pytest.mark.parametrize("seats", [set(), {Position.BTN}])
def test_flop_positions_needs_two_players(seats: set[Position]) -> None:
    with pytest.raises(ValueError):
        flop_positions(seats)
