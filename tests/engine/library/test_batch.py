"""Tests for the library batch: idempotent and resumable (FR-013, US5 scenarios 1 to 4)."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from engine.game import GameConfig, build_tree
from engine.library import (
    BatchEvent,
    BatchStatus,
    ConvergenceChecked,
    DepthFinished,
    DepthStarted,
    FileSolutionStore,
    SolveParams,
    engine_version,
    fingerprint,
    run_batch,
)
from engine.library import batch as batch_module
from engine.realization import default_profile
from engine.solver import EquityTables


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


TABLES = strength_tables([3.0, 1.0, 2.0, 0.7])
PARAMS = SolveParams(max_iterations=60, check_every=20)
TWO_DEPTHS = (GameConfig.equal_stacks(5.0), GameConfig.equal_stacks(12.0))


def batch(store: FileSolutionStore, configs: Any = TWO_DEPTHS, **kwargs: Any) -> Any:
    options: dict[str, Any] = {"params": PARAMS} | kwargs
    return run_batch(configs, TABLES, default_profile(), store=store, **options)


def snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    """Content and modification time of every solution file."""
    return {
        str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "index.sqlite"
    }


# --- US5 scenario 1: every depth solved and stored ---------------------------------------


def test_two_depths_give_two_stored_solutions(tmp_path: Path) -> None:
    store = FileSolutionStore(tmp_path)
    report = batch(store)
    assert [entry.status for entry in report.entries] == [BatchStatus.SOLVED] * 2
    assert report.solved == 2 and report.skipped == 0
    summaries = store.list_solutions()
    assert [s.stacks[0] for s in summaries] == [5.0, 12.0]
    for entry, summary in zip(report.entries, summaries, strict=True):
        assert entry.summary == summary
        assert entry.seconds > 0
        loaded = store.load(summary.fingerprint)
        assert loaded.iterations == summary.iterations > 0
        assert loaded.duration_seconds > 0
        assert loaded.exploitability.percent == pytest.approx(summary.nash_conv_percent)


def test_the_batch_uses_the_fingerprint_of_the_inputs(tmp_path: Path) -> None:
    report = batch(FileSolutionStore(tmp_path))
    for config, entry in zip(TWO_DEPTHS, report.entries, strict=True):
        expected = fingerprint(
            build_tree(config), default_profile(), PARAMS, TABLES.digest, engine_version()
        )
        assert entry.summary.fingerprint == expected


def test_depths_are_solved_in_the_given_order(tmp_path: Path) -> None:
    configs = (GameConfig.equal_stacks(12.0), GameConfig.equal_stacks(5.0))
    started: list[float] = []

    def on_event(event: BatchEvent) -> None:
        if isinstance(event, DepthStarted):
            started.append(event.config.stacks[0])
            assert event.total == 2

    batch(FileSolutionStore(tmp_path), configs, on_event=on_event)
    assert started == [12.0, 5.0]


# --- US5 scenario 2: nothing recomputed on a rerun ---------------------------------------


def test_a_rerun_recomputes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = FileSolutionStore(tmp_path)
    first = batch(store)
    before = snapshot(tmp_path)

    def no_solve(*args: object, **kwargs: object) -> None:
        raise AssertionError("solve must not be called")

    monkeypatch.setattr(batch_module, "solve", no_solve)
    second = batch(store)
    assert [entry.status for entry in second.entries] == [BatchStatus.SKIPPED] * 2
    assert second.solved == 0 and second.skipped == 2
    assert [e.summary for e in second.entries] == [e.summary for e in first.entries]
    assert snapshot(tmp_path) == before


def test_other_parameters_give_new_solutions(tmp_path: Path) -> None:
    store = FileSolutionStore(tmp_path)
    batch(store)
    report = batch(store, params=SolveParams(max_iterations=40, check_every=20))
    assert report.solved == 2
    assert len(store.list_solutions()) == 4


# --- US5 scenario 3: a solution above the threshold is not published ---------------------


def test_a_solution_above_the_threshold_is_marked_non_conforming(tmp_path: Path) -> None:
    store = FileSolutionStore(tmp_path)
    report = batch(
        store,
        (GameConfig.equal_stacks(5.0), GameConfig.equal_stacks(20.0)),
        params=SolveParams(max_iterations=1, check_every=1),
    )
    rough = report.entries[1]
    assert rough.status is BatchStatus.SOLVED
    assert not rough.summary.publishable
    assert rough.summary.nash_conv_percent >= 0.5
    assert report.non_conforming == (rough,)
    published = [s.fingerprint for s in store.list_solutions(publishable_only=True)]
    assert rough.summary.fingerprint not in published
    assert store.contains(rough.summary.fingerprint)


# --- US5 scenario 4: an interrupted batch resumes ----------------------------------------


def test_an_interrupted_batch_resumes_at_the_missing_depths(tmp_path: Path) -> None:
    store = FileSolutionStore(tmp_path)

    def interrupt_the_second_depth(event: BatchEvent) -> None:
        if isinstance(event, ConvergenceChecked) and event.config.stacks[0] == 12.0:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        batch(store, on_event=interrupt_the_second_depth)
    assert [s.stacks[0] for s in store.list_solutions()] == [5.0]
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp")]

    report = batch(store)
    assert [entry.status for entry in report.entries] == [BatchStatus.SKIPPED, BatchStatus.SOLVED]
    assert [s.stacks[0] for s in store.list_solutions()] == [5.0, 12.0]


# --- Events ------------------------------------------------------------------------------


def test_events_describe_the_progress(tmp_path: Path) -> None:
    store = FileSolutionStore(tmp_path)
    batch(store, TWO_DEPTHS[:1])
    events: list[BatchEvent] = []
    batch(store, TWO_DEPTHS, on_event=events.append)

    kinds = [type(event).__name__ for event in events]
    assert kinds[:2] == ["DepthStarted", "DepthFinished"]
    assert kinds[2] == "DepthStarted"
    assert set(kinds[3:-1]) == {"ConvergenceChecked"}
    assert kinds[-1] == "DepthFinished"

    first, second = events[0], events[2]
    assert isinstance(first, DepthStarted) and isinstance(second, DepthStarted)
    assert first.already_stored and not second.already_stored
    assert (first.index, second.index) == (1, 2)
    checks = [e for e in events if isinstance(e, ConvergenceChecked)]
    assert [e.iterations for e in checks] == list(range(20, 20 * len(checks) + 1, 20))
    finished = events[-1]
    assert isinstance(finished, DepthFinished)
    assert finished.entry.status is BatchStatus.SOLVED


def test_an_empty_batch_does_nothing(tmp_path: Path) -> None:
    report = batch(FileSolutionStore(tmp_path), ())
    assert report.entries == ()
    assert report.solved == report.skipped == 0
