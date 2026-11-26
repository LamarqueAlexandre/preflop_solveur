"""Tests for GameConfig, the sizing table by stack tranche and the all-in conversion."""

import dataclasses

import pytest

from engine.game import (
    STACK_GRID,
    GameConfig,
    SizingTable,
    Tranche,
    TrancheSizings,
    default_configs,
    default_sizing_table,
    tranche_of,
)

# --- Tranches ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stack", "expected"),
    [
        (3.0, Tranche.SHORT),
        (8.0, Tranche.SHORT),
        (9.0, Tranche.MEDIUM),
        (15.0, Tranche.MEDIUM),
        (16.0, Tranche.DEEP),
        (25.0, Tranche.DEEP),
    ],
)
def test_tranche_bounds(stack: float, expected: Tranche) -> None:
    assert tranche_of(stack) is expected


@pytest.mark.parametrize("stack", [0.0, -1.0])
def test_tranche_rejects_non_positive_stacks(stack: float) -> None:
    with pytest.raises(ValueError):
        tranche_of(stack)


# --- Default sizings (FR-004, D-011) ------------------------------------------------------


def test_short_tranche_has_no_sized_raise() -> None:
    # <= 8bb: open fold / limp / all-in; vs raise fold / call / all-in; isolation all-in.
    short = default_sizing_table().for_tranche(Tranche.SHORT)
    assert short.open_raises == ()
    assert short.three_bet_multipliers == ()
    assert short.isolation_base is None
    assert short.isolation_size(1) is None
    assert short.isolation_size(2) is None


def test_medium_tranche_min_raise_and_all_in_three_bet() -> None:
    # 9-15bb: open fold / limp / 2x / all-in; vs raise fold / call / 3-bet all-in.
    medium = default_sizing_table().for_tranche(Tranche.MEDIUM)
    assert medium.open_raises == (2.0,)
    assert medium.three_bet_multipliers == ()
    assert medium.three_bet_sizes(2.0) == ()


def test_deep_tranche_sizings() -> None:
    # > 15bb: open 2x / 2.5x; 3-bet to 3x the raise; facing a 3-bet: 4-bet all-in only.
    deep = default_sizing_table().for_tranche(Tranche.DEEP)
    assert deep.open_raises == (2.0, 2.5)
    assert deep.three_bet_multipliers == (3.0,)
    assert deep.three_bet_sizes(2.0) == (6.0,)
    assert deep.three_bet_sizes(2.5) == (7.5,)


@pytest.mark.parametrize("tranche", [Tranche.MEDIUM, Tranche.DEEP])
def test_isolation_is_3bb_plus_1bb_per_extra_limper(tranche: Tranche) -> None:
    sizings = default_sizing_table().for_tranche(tranche)
    assert sizings.isolation_size(1) == 3.0
    assert sizings.isolation_size(2) == 4.0


def test_isolation_needs_at_least_one_limper() -> None:
    sizings = default_sizing_table().for_tranche(Tranche.DEEP)
    with pytest.raises(ValueError):
        sizings.isolation_size(0)


# --- GameConfig ----------------------------------------------------------------------------


def test_equal_stacks_config() -> None:
    config = GameConfig.equal_stacks(20.0)
    assert config.stacks == (20.0, 20.0, 20.0)  # BTN, SB, BB
    assert config.small_blind == 0.5
    assert config.big_blind == 1.0
    assert config.all_in_threshold == 1.0
    assert config.realization_profile == "default"
    assert config.sizing_table == default_sizing_table()


def test_config_tranche_and_sizings() -> None:
    assert GameConfig.equal_stacks(8.0).tranche is Tranche.SHORT
    assert GameConfig.equal_stacks(12.0).tranche is Tranche.MEDIUM
    deep = GameConfig.equal_stacks(16.0)
    assert deep.tranche is Tranche.DEEP
    assert deep.sizings == default_sizing_table().for_tranche(Tranche.DEEP)


def test_config_is_immutable() -> None:
    config = GameConfig.equal_stacks(10.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.big_blind = 2.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.sizings.open_raises = (3.0,)  # type: ignore[misc]


def test_configs_are_hashable_and_comparable() -> None:
    assert GameConfig.equal_stacks(10.0) == GameConfig.equal_stacks(10.0)
    assert len({GameConfig.equal_stacks(10.0), GameConfig.equal_stacks(10.0)}) == 1


# --- All-in conversion (D-011) -------------------------------------------------------------


def test_raise_leaving_less_than_1bb_becomes_all_in() -> None:
    config = GameConfig.equal_stacks(9.0)
    assert config.raise_to(8.2, stack=9.0) == 9.0


def test_raise_leaving_exactly_1bb_is_kept() -> None:
    config = GameConfig.equal_stacks(9.0)
    assert config.raise_to(8.0, stack=9.0) == 8.0


def test_raise_above_the_stack_becomes_all_in() -> None:
    config = GameConfig.equal_stacks(9.0)
    assert config.raise_to(12.0, stack=9.0) == 9.0


def test_ordinary_raise_is_unchanged() -> None:
    config = GameConfig.equal_stacks(20.0)
    assert config.raise_to(7.5, stack=20.0) == 7.5


def test_default_grid_never_needs_the_conversion() -> None:
    # The largest default raise is the isolation to 4bb at 9bb: 5bb behind.
    for config in default_configs():
        sizings = config.sizings
        stack = config.stacks[0]
        candidates = [*sizings.open_raises]
        for opening in sizings.open_raises:
            candidates += sizings.three_bet_sizes(opening)
        candidates += [s for s in (sizings.isolation_size(1), sizings.isolation_size(2)) if s]
        for amount in candidates:
            assert config.raise_to(amount, stack) == amount


# --- Stack grid (FR-003) -------------------------------------------------------------------


def test_stack_grid_is_3_to_25bb_by_1bb() -> None:
    assert STACK_GRID == tuple(float(s) for s in range(3, 26))
    assert len(STACK_GRID) == 23


def test_default_configs_cover_the_grid_with_equal_stacks() -> None:
    configs = default_configs()
    assert len(configs) == 23
    assert [c.stacks for c in configs] == [(s, s, s) for s in STACK_GRID]
    assert all(c.small_blind == 0.5 and c.big_blind == 1.0 for c in configs)


# --- Validation ----------------------------------------------------------------------------


@pytest.mark.parametrize("stacks", [(0.0, 10.0, 10.0), (10.0, -1.0, 10.0), (10.0, 10.0, 0.5)])
def test_rejects_stacks_below_the_big_blind(stacks: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        GameConfig(stacks=stacks)


@pytest.mark.parametrize(("small", "big"), [(1.0, 1.0), (0.0, 1.0), (0.5, 0.0)])
def test_rejects_inconsistent_blinds(small: float, big: float) -> None:
    with pytest.raises(ValueError):
        GameConfig(stacks=(10.0, 10.0, 10.0), small_blind=small, big_blind=big)


def test_rejects_negative_threshold() -> None:
    with pytest.raises(ValueError):
        GameConfig(stacks=(10.0, 10.0, 10.0), all_in_threshold=-0.5)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"open_raises": (2.5, 2.0)},  # not increasing
        {"open_raises": (2.0, 2.0)},  # duplicated
        {"open_raises": (1.5,)},  # below a min-raise (2bb)
        {"three_bet_multipliers": (1.5,)},  # below a min re-raise
        {"isolation_base": 1.5},  # below a min-raise
        {"isolation_per_extra_limper": -1.0},
    ],
)
def test_rejects_invalid_tranche_sizings(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        TrancheSizings(**kwargs)  # type: ignore[arg-type]


def test_custom_sizing_table() -> None:
    custom = SizingTable(
        short=TrancheSizings(),
        medium=TrancheSizings(open_raises=(2.0,), isolation_base=3.0),
        deep=TrancheSizings(open_raises=(2.25,), three_bet_multipliers=(2.8,), isolation_base=3.5),
    )
    config = GameConfig(stacks=(20.0, 20.0, 20.0), sizing_table=custom)
    assert config.sizings.open_raises == (2.25,)
    assert config.sizings.three_bet_sizes(2.25) == pytest.approx((6.3,))
    assert config.sizings.isolation_size(2) == 4.5
