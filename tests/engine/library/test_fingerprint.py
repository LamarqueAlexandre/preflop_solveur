"""Tests for the configuration fingerprint (FR-012, principle III, D-016).

Same inputs -> same fingerprint; any change to the config, the tree, the
realization profile, the convergence parameters, the engine version or the
equity tensors -> another fingerprint.
"""

import re
from collections.abc import Callable
from dataclasses import replace
from types import MappingProxyType
from typing import Any

import pytest

from engine.game import GameConfig, GameTree, build_tree
from engine.game.config import default_sizing_table
from engine.library import SolveParams
from engine.library.fingerprint import FINGERPRINT_SCHEMA, fingerprint, fingerprint_data
from engine.library.serialization import profile_from_data, profile_to_data
from engine.realization import RealizationProfile, default_profile
from engine.solver import DCFRParams

DIGEST = "ab" * 32
VERSION = "0.1.0"


def base_inputs() -> dict[str, Any]:
    return {
        "tree": build_tree(GameConfig.equal_stacks(12.0)),
        "profile": default_profile(),
        "params": SolveParams(),
        "equity_digest": DIGEST,
        "engine_version": VERSION,
    }


def with_factor(profile: RealizationProfile, factor: float) -> RealizationProfile:
    data = profile_to_data(profile)
    entries = [dict(entry) for entry in data["entries"]]
    entries[0]["factor"] = factor
    return profile_from_data(dict(data, entries=entries))


def with_version(profile: RealizationProfile, version: str) -> RealizationProfile:
    return profile_from_data(dict(profile_to_data(profile), version=version))


def with_config(**changes: Any) -> GameTree:
    return build_tree(replace(GameConfig.equal_stacks(12.0), **changes))


def renamed_root_action() -> GameTree:
    """Same config, one node changed: a tree built by another version of the builder."""
    tree = build_tree(GameConfig.equal_stacks(12.0))
    nodes = dict(tree.nodes)
    root = nodes["root"]
    nodes["root"] = replace(root, raise_level=root.raise_level + 1)
    return GameTree(config=tree.config, nodes=MappingProxyType(nodes))


def test_fingerprint_is_a_sha256_hex_digest() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint(**base_inputs()))


def test_same_inputs_give_the_same_fingerprint() -> None:
    assert fingerprint(**base_inputs()) == fingerprint(**base_inputs())


def test_integer_and_float_stacks_give_the_same_fingerprint() -> None:
    integer = dict(base_inputs(), tree=build_tree(GameConfig.equal_stacks(12)))
    assert fingerprint(**integer) == fingerprint(**base_inputs())


def test_profile_entry_order_does_not_matter() -> None:
    data = profile_to_data(default_profile())
    shuffled = profile_from_data(dict(data, entries=list(reversed(data["entries"]))))
    assert fingerprint(**dict(base_inputs(), profile=shuffled)) == fingerprint(**base_inputs())


CHANGES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "stack": lambda i: dict(i, tree=build_tree(GameConfig.equal_stacks(13.0))),
    "one stack": lambda i: dict(i, tree=with_config(stacks=(12.0, 12.0, 13.0))),
    "small blind": lambda i: dict(i, tree=with_config(small_blind=0.4)),
    "big blind": lambda i: dict(i, tree=with_config(big_blind=1.2)),
    "all-in threshold": lambda i: dict(i, tree=with_config(all_in_threshold=1.5)),
    "sizing": lambda i: dict(
        i,
        tree=with_config(
            sizing_table=replace(
                default_sizing_table(),
                medium=replace(default_sizing_table().medium, isolation_base=3.5),
            )
        ),
    ),
    "profile name in the config": lambda i: dict(i, tree=with_config(realization_profile="x")),
    "tree": lambda i: dict(i, tree=renamed_root_action()),
    "profile factor": lambda i: dict(i, profile=with_factor(i["profile"], 1.234)),
    "profile version": lambda i: dict(i, profile=with_version(i["profile"], "9.9.9")),
    "max iterations": lambda i: dict(i, params=replace(i["params"], max_iterations=2001)),
    "target": lambda i: dict(i, params=replace(i["params"], target_percent=0.05)),
    "check every": lambda i: dict(i, params=replace(i["params"], check_every=50)),
    "alpha": lambda i: dict(i, params=replace(i["params"], dcfr=DCFRParams(alpha=1.0))),
    "beta": lambda i: dict(i, params=replace(i["params"], dcfr=DCFRParams(beta=0.5))),
    "gamma": lambda i: dict(i, params=replace(i["params"], dcfr=DCFRParams(gamma=3.0))),
    "engine version": lambda i: dict(i, engine_version="0.2.0"),
    "equity tensors": lambda i: dict(i, equity_digest="cd" * 32),
}


@pytest.mark.parametrize("change", list(CHANGES), ids=list(CHANGES))
def test_any_change_gives_another_fingerprint(change: str) -> None:
    changed = CHANGES[change](base_inputs())
    assert fingerprint(**changed) != fingerprint(**base_inputs())


def test_fingerprint_data_holds_every_input() -> None:
    data = fingerprint_data(**base_inputs())
    assert data["schema"] == FINGERPRINT_SCHEMA == 1
    assert data["engine_version"] == VERSION
    assert data["equity_digest"] == DIGEST
    assert set(data) == {
        "schema",
        "config",
        "tree",
        "profile",
        "params",
        "engine_version",
        "equity_digest",
    }
