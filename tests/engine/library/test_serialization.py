"""Tests for the JSON form of configs, trees, profiles and parameters (FR-012, D-016)."""

import json

import pytest

from engine.game import GameConfig, build_tree
from engine.game.config import SizingTable, TrancheSizings
from engine.library import SolveParams
from engine.library.serialization import (
    canonical_json,
    config_from_data,
    config_to_data,
    exploitability_from_data,
    exploitability_to_data,
    params_from_data,
    params_to_data,
    profile_from_data,
    profile_to_data,
    tree_from_data,
    tree_to_data,
)
from engine.realization import default_profile
from engine.solver import DCFRParams, Exploitability


def custom_config() -> GameConfig:
    table = SizingTable(
        short=TrancheSizings(),
        medium=TrancheSizings(open_raises=(2.0,), isolation_base=3.0),
        deep=TrancheSizings(
            open_raises=(2.0, 2.5),
            three_bet_multipliers=(3.0,),
            isolation_base=3.0,
            isolation_per_extra_limper=0.5,
        ),
    )
    return GameConfig(
        stacks=(12.0, 15.0, 20.0),
        sizing_table=table,
        all_in_threshold=0.5,
        realization_profile="custom",
    )


@pytest.mark.parametrize("config", [GameConfig.equal_stacks(10.0), custom_config()])
def test_config_round_trip(config: GameConfig) -> None:
    data = config_to_data(config)
    assert config_from_data(json.loads(json.dumps(data))) == config


def test_config_amounts_are_written_as_floats() -> None:
    assert config_to_data(GameConfig.equal_stacks(10)) == config_to_data(
        GameConfig.equal_stacks(10.0)
    )
    assert config_to_data(GameConfig.equal_stacks(10))["stacks"] == [10.0, 10.0, 10.0]


@pytest.mark.parametrize("stack", [5.0, 12.0, 20.0])
def test_tree_round_trip(stack: float) -> None:
    tree = build_tree(GameConfig.equal_stacks(stack))
    data = json.loads(json.dumps(tree_to_data(tree)))
    loaded = tree_from_data(tree.config, data)
    assert loaded.config == tree.config
    assert list(loaded.nodes) == list(tree.nodes)
    assert list(loaded) == list(tree)


def test_profile_round_trip_and_canonical_order() -> None:
    profile = default_profile()
    data = profile_to_data(profile)
    loaded = profile_from_data(json.loads(json.dumps(data)))
    assert loaded == profile
    assert dict(loaded.factors) == dict(profile.factors)

    shuffled = dict(data, entries=list(reversed(data["entries"])))
    assert profile_to_data(profile_from_data(shuffled)) == data


def test_params_round_trip() -> None:
    params = SolveParams(
        max_iterations=300,
        target_percent=0.05,
        check_every=25,
        dcfr=DCFRParams(alpha=1.0, beta=0.5, gamma=3.0),
    )
    assert params_from_data(json.loads(json.dumps(params_to_data(params)))) == params


def test_exploitability_round_trip() -> None:
    result = Exploitability(
        ev=(0.25, -0.125, -0.125), best_response_values=(0.3, -0.1, -0.1), starting_pot=1.5
    )
    data = json.loads(json.dumps(exploitability_to_data(result)))
    assert exploitability_from_data(data) == result
    assert data["percent"] == pytest.approx(result.percent)


def test_canonical_json_ignores_key_order_and_spacing() -> None:
    assert canonical_json({"b": 1, "a": [1.5, None]}) == '{"a":[1.5,null],"b":1}'
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json({"a": float("nan")})
