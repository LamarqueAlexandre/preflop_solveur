"""Tests for the file-based solution store (FR-012, FR-013, principles III and VII, D-016)."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Final

import numpy as np
import pytest

from engine.game import GameConfig, build_tree
from engine.library import (
    STORE_FORMAT_VERSION,
    FileSolutionStore,
    Solution,
    SolutionStore,
    SolveParams,
    StoreError,
    solution_fingerprint,
    solve,
)
from engine.realization import default_profile
from engine.solver import EquityTables

LEGACY: Final = Path(__file__).parent / "data" / "legacy_store"
"""A solution written by engine version 0.0.0, frozen in the repository."""


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


TABLES = strength_tables([3.0, 1.0, 2.0, 0.7])


def solved(stack: float, max_iterations: int = 50) -> Solution:
    tree = build_tree(GameConfig.equal_stacks(stack))
    params = SolveParams(max_iterations=max_iterations, check_every=10)
    return solve(tree, TABLES, default_profile(), params)


@pytest.fixture(scope="module")
def solution() -> Solution:
    return solved(12.0)


@pytest.fixture(scope="module")
def rough() -> Solution:
    """Stopped after one iteration: not publishable."""
    return solve(
        build_tree(GameConfig.equal_stacks(20.0)),
        TABLES,
        default_profile(),
        SolveParams(max_iterations=1, check_every=1),
    )


def assert_same_solution(loaded: Solution, original: Solution) -> None:
    assert loaded.config == original.config
    assert list(loaded.tree) == list(original.tree)
    assert loaded.profile == original.profile
    assert loaded.params == original.params
    assert loaded.iterations == original.iterations
    assert loaded.duration_seconds == original.duration_seconds
    assert loaded.exploitability == original.exploitability
    assert loaded.engine_version == original.engine_version
    assert loaded.equity_digest == original.equity_digest
    assert list(loaded.strategy) == list(original.strategy)
    for node_id, played in original.strategy.items():
        np.testing.assert_array_equal(loaded.strategy[node_id], played)
    assert loaded.values.node_ids == original.values.node_ids
    for name in ("reach", "opponent_mass", "ev"):
        np.testing.assert_array_equal(
            getattr(loaded.values, name), getattr(original.values, name)
        )  # NaN compare equal here
    np.testing.assert_array_equal(loaded.hand_mass, original.hand_mass)


# --- Round trip --------------------------------------------------------------------------


def test_store_is_a_solution_store(tmp_path: Path) -> None:
    assert isinstance(FileSolutionStore(tmp_path), SolutionStore)


def test_round_trip_gives_an_identical_solution(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    fingerprint = store.save(solution)
    assert fingerprint == solution_fingerprint(solution)
    assert_same_solution(store.load(fingerprint), solution)
    assert_same_solution(FileSolutionStore(tmp_path).load(fingerprint), solution)


def test_round_trip_keeps_undefined_evs(tmp_path: Path) -> None:
    store = FileSolutionStore(tmp_path)
    original = solved(20.0, max_iterations=10)
    loaded = store.load(store.save(original))
    np.testing.assert_array_equal(np.isnan(loaded.values.ev), np.isnan(original.values.ev))


def test_loaded_arrays_are_read_only(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    loaded = store.load(store.save(solution))
    with pytest.raises(ValueError):
        loaded.values.ev[0, 0, 0] = 1.0
    with pytest.raises(ValueError):
        next(iter(loaded.strategy.values()))[0, 0] = 1.0


def test_layout_is_one_directory_per_fingerprint(tmp_path: Path, solution: Solution) -> None:
    fingerprint = FileSolutionStore(tmp_path).save(solution)
    directory = tmp_path / fingerprint
    assert sorted(p.name for p in directory.iterdir()) == ["arrays.npz", "manifest.json"]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format_version"] == STORE_FORMAT_VERSION == 1
    assert manifest["fingerprint"] == fingerprint
    assert manifest["engine_version"] == solution.engine_version
    assert manifest["publishable"] is True
    assert manifest["exploitability"]["percent"] == pytest.approx(solution.exploitability.percent)
    assert (tmp_path / "index.sqlite").is_file()


# --- Idempotence and atomicity -----------------------------------------------------------


def test_contains_and_idempotent_save(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    fingerprint = solution_fingerprint(solution)
    assert not store.contains(fingerprint)
    assert store.save(solution) == fingerprint
    assert store.contains(fingerprint)
    manifest = tmp_path / fingerprint / "manifest.json"
    before = manifest.stat().st_mtime_ns, manifest.read_bytes()
    assert store.save(replace(solution, duration_seconds=123.0)) == fingerprint
    assert (manifest.stat().st_mtime_ns, manifest.read_bytes()) == before
    assert len(store.list_solutions()) == 1


def test_interrupted_writes_are_ignored(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    leftover = tmp_path / ".tmp-interrupted"
    leftover.mkdir()
    (leftover / "arrays.npz").write_bytes(b"partial")
    assert store.list_solutions() == []
    store.rebuild_index()
    assert store.list_solutions() == []
    store.save(solution)
    assert [s.fingerprint for s in store.list_solutions()] == [solution_fingerprint(solution)]


def test_no_temporary_directory_is_left_after_a_save(tmp_path: Path, solution: Solution) -> None:
    FileSolutionStore(tmp_path).save(solution)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp")]


# --- Index -------------------------------------------------------------------------------


def test_list_solutions_summarizes_and_filters(
    tmp_path: Path, solution: Solution, rough: Solution
) -> None:
    store = FileSolutionStore(tmp_path)
    good, bad = store.save(solution), store.save(rough)
    summaries = {s.fingerprint: s for s in store.list_solutions()}
    assert set(summaries) == {good, bad}
    summary = summaries[good]
    assert summary.stacks == (12.0, 12.0, 12.0)
    assert summary.tranche == "medium"
    assert summary.profile_name == "default"
    assert summary.profile_version == solution.profile_version
    assert summary.engine_version == solution.engine_version
    assert summary.format_version == STORE_FORMAT_VERSION
    assert summary.nash_conv_percent == pytest.approx(solution.exploitability.percent)
    assert summary.iterations == solution.iterations
    assert summary.publishable
    assert summary.created_at
    assert not summaries[bad].publishable
    assert [s.fingerprint for s in store.list_solutions(publishable_only=True)] == [good]


def test_list_is_sorted_by_stack(tmp_path: Path, solution: Solution, rough: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    store.save(rough)
    store.save(solution)
    assert [s.stacks[0] for s in store.list_solutions()] == [12.0, 20.0]


def test_rebuild_index_restores_a_deleted_index(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    store.save(solution)
    expected = store.list_solutions()
    (tmp_path / "index.sqlite").unlink()
    reopened = FileSolutionStore(tmp_path)
    assert reopened.list_solutions() == []
    reopened.rebuild_index()
    assert reopened.list_solutions() == expected


# --- Errors ------------------------------------------------------------------------------


def test_loading_an_unknown_fingerprint_fails(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        FileSolutionStore(tmp_path).load("0" * 64)


def test_corrupted_arrays_are_detected(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    fingerprint = store.save(solution)
    (tmp_path / fingerprint / "arrays.npz").write_bytes(b"corrupted")
    with pytest.raises(StoreError, match="checksum"):
        store.load(fingerprint)


def test_an_unknown_format_version_is_rejected(tmp_path: Path, solution: Solution) -> None:
    store = FileSolutionStore(tmp_path)
    fingerprint = store.save(solution)
    path = tmp_path / fingerprint / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["format_version"] = 99
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StoreError, match="format"):
        store.load(fingerprint)


# --- Solutions written by an older engine ------------------------------------------------


def test_a_solution_of_an_older_version_stays_readable(tmp_path: Path) -> None:
    shutil.copytree(LEGACY, tmp_path, dirs_exist_ok=True)
    store = FileSolutionStore(tmp_path)
    store.rebuild_index()
    (summary,) = store.list_solutions()
    assert summary.engine_version == "0.0.0"
    loaded = store.load(summary.fingerprint)
    assert loaded.engine_version == "0.0.0"
    assert loaded.config == GameConfig.equal_stacks(5.0)
    assert loaded.node("root").strategy.shape[1] == 4
    assert sum(loaded.root_ev()) == pytest.approx(0.0, abs=1e-9)


def test_the_legacy_fingerprint_differs_from_the_current_engine(tmp_path: Path) -> None:
    shutil.copytree(LEGACY, tmp_path, dirs_exist_ok=True)
    store = FileSolutionStore(tmp_path)
    store.rebuild_index()
    (summary,) = store.list_solutions()
    current = replace(store.load(summary.fingerprint), engine_version="0.1.0")
    assert solution_fingerprint(current) != summary.fingerprint
