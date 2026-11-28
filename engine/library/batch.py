"""Library batch: solve and store each depth, idempotent and resumable (FR-013, US5).

For each configuration, the fingerprint is computed before solving (D-016):
a fingerprint already in the store is skipped, so a rerun recomputes nothing
and an interrupted batch resumes at the depths not stored yet. Each solution
is written atomically, so at most the depth being solved is lost.

A solution that misses the publication threshold is stored as non-conforming
(not published). Same inputs, same fingerprint: it is not recomputed by a
rerun; changing a convergence parameter gives a new fingerprint.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from engine.game.config import GameConfig
from engine.game.tree import build_tree
from engine.library.fingerprint import fingerprint
from engine.library.solution import SolveParams, engine_version, solve
from engine.library.store import SolutionStore, SolutionSummary
from engine.realization.profile import RealizationProfile
from engine.solver import EquityTables, Exploitability


class BatchStatus(Enum):
    SOLVED = "solved"
    SKIPPED = "skipped"  # already in the store


@dataclass(frozen=True)
class BatchEntry:
    """Outcome of one depth; ``seconds`` is the time this batch spent on it."""

    config: GameConfig
    status: BatchStatus
    summary: SolutionSummary
    seconds: float


@dataclass(frozen=True)
class BatchReport:
    entries: tuple[BatchEntry, ...]

    @property
    def solved(self) -> int:
        return sum(entry.status is BatchStatus.SOLVED for entry in self.entries)

    @property
    def skipped(self) -> int:
        return sum(entry.status is BatchStatus.SKIPPED for entry in self.entries)

    @property
    def non_conforming(self) -> tuple[BatchEntry, ...]:
        """Stored solutions above the publication threshold (not published)."""
        return tuple(entry for entry in self.entries if not entry.summary.publishable)

    @property
    def seconds(self) -> float:
        return sum(entry.seconds for entry in self.entries)


@dataclass(frozen=True)
class DepthStarted:
    """Depth ``index`` of ``total`` (from 1) is about to be solved or skipped."""

    index: int
    total: int
    config: GameConfig
    fingerprint: str
    already_stored: bool


@dataclass(frozen=True)
class ConvergenceChecked:
    config: GameConfig
    iterations: int
    exploitability: Exploitability


@dataclass(frozen=True)
class DepthFinished:
    entry: BatchEntry


BatchEvent = DepthStarted | ConvergenceChecked | DepthFinished


def run_batch(
    configs: Iterable[GameConfig],
    tables: EquityTables,
    profile: RealizationProfile,
    store: SolutionStore,
    params: SolveParams | None = None,
    on_event: Callable[[BatchEvent], None] | None = None,
) -> BatchReport:
    """Solve and store every configuration missing from ``store``, in the given order."""
    params = params or SolveParams()
    configs = tuple(configs)
    version = engine_version()

    def emit(event: BatchEvent) -> None:
        if on_event is not None:
            on_event(event)

    entries: list[BatchEntry] = []
    for index, config in enumerate(configs, start=1):
        start = time.perf_counter()
        tree = build_tree(config)
        key = fingerprint(tree, profile, params, tables.digest, version)
        stored = store.contains(key)
        emit(DepthStarted(index, len(configs), config, key, stored))
        if stored:
            status = BatchStatus.SKIPPED
        else:

            def progress(
                iterations: int, result: Exploitability, config: GameConfig = config
            ) -> None:
                emit(ConvergenceChecked(config, iterations, result))

            saved = store.save(solve(tree, tables, profile, params, progress))
            if saved != key:  # the solution records the inputs it was given
                raise RuntimeError(f"fingerprint mismatch: expected {key}, stored {saved}")
            status = BatchStatus.SOLVED
        entry = BatchEntry(config, status, store.summary(key), time.perf_counter() - start)
        entries.append(entry)
        emit(DepthFinished(entry))
    return BatchReport(tuple(entries))
