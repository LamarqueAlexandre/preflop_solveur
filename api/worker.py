"""Best-response jobs, run in a worker process (principle VII, FR-016).

The worker loads the solution and the equity tensors itself, calls the engine
and writes the outcome to the job store. It only reshapes engine arrays.

Process-local cache: the tensors (~1 s to load) and the ``TerminalValues`` of
the last solutions (their flop-share cache makes the first best response
~2.5 s, the next ones ~0.2 s at 25bb) are kept for the life of the worker
process. This is a computation cache, not API state: losing it costs time only.
"""

import math
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

from api.jobs import JobStore
from api.schemas import (
    ActionOut,
    BestResponseOut,
    HandGainOut,
    HeroHandOut,
    HeroNodeOut,
    PositionName,
)
from engine.best_response import ExploitResult, exploit_solution
from engine.cards import CLASS_WEIGHTS, format_class, grid_position
from engine.equity.storage import load_tensors
from engine.game.tree import Position
from engine.library import Solution, SolutionStore
from engine.solver import EquityTables, TerminalValues

BEST_RESPONSE: Final = "best_response"
_TERMINAL_CACHE_SIZE: Final = 4


class EquitySource(ABC):
    """Where a worker finds the equity tables; picklable and hashable (cache key)."""

    @abstractmethod
    def load(self) -> EquityTables: ...


@dataclass(frozen=True)
class DirectoryEquity(EquitySource):
    """Tensors stored by ``engine.equity.storage`` in ``directory``."""

    directory: Path

    def load(self) -> EquityTables:
        return EquityTables.from_stored(load_tensors(self.directory))


@dataclass(frozen=True, eq=False)
class ArrayEquity(EquitySource):
    """Tensors given as arrays (small test tables); compared by identity."""

    w: ArrayLike = field(repr=False)
    e3: ArrayLike = field(repr=False)
    e2: ArrayLike = field(repr=False)

    def load(self) -> EquityTables:
        return EquityTables.from_arrays(self.w, self.e3, self.e2)


@lru_cache(maxsize=1)
def _tables(source: EquitySource) -> EquityTables:
    return source.load()


_terminal_cache: OrderedDict[tuple[EquitySource, str], TerminalValues] = OrderedDict()
"""Worker-process cache, by (equity source, solution fingerprint)."""


def _terminal_values(source: EquitySource, fingerprint: str, solution: Solution) -> TerminalValues:
    key = (source, fingerprint)
    if key in _terminal_cache:
        _terminal_cache.move_to_end(key)
        return _terminal_cache[key]
    tables = _tables(source)
    if tables.digest != solution.equity_digest:
        raise ValueError(
            "the equity tensors of the API are not those the solution was computed with "
            f"(digest {tables.digest[:12]}… instead of {solution.equity_digest[:12]}…)"
        )
    values = TerminalValues(solution.tree, tables, solution.profile)
    _terminal_cache[key] = values
    if len(_terminal_cache) > _TERMINAL_CACHE_SIZE:
        _terminal_cache.popitem(last=False)
    return values


def _optional(value: float) -> float | None:
    """JSON-safe float: NaN (undefined) becomes None."""
    return float(value) if math.isfinite(value) else None


def _floats(values: NDArray[np.float64]) -> list[float]:
    return [float(v) for v in values.tolist()]


def best_response_out(
    solution: Solution, fingerprint: str, result: ExploitResult
) -> BestResponseOut:
    """Engine result reshaped per hand class and per hero node."""
    n_classes = len(result.hand_gain)
    hands = [
        HandGainOut(
            hand=format_class(h),
            row=grid_position(h)[0],
            col=grid_position(h)[1],
            combos=int(CLASS_WEIGHTS[h]),
            gain=_optional(result.hand_gain[h]),
        )
        for h in range(n_classes)
    ]
    nodes = [
        HeroNodeOut(
            node_id=node_id,
            actions=[
                ActionOut(kind=a.kind.value, amount=a.amount, label=a.token, child_id=child)
                for a, child in zip(node.actions, solution.tree.node(node_id).children, strict=True)
            ],
            hands=[
                HeroHandOut(
                    hand=format_class(h),
                    equilibrium=_floats(node.equilibrium[:, h]),
                    best=_floats(node.best[:, h]),
                    frequency_gap=_floats(node.frequency_gap[:, h]),
                    ev_gain=_optional(node.ev_gain[h]),
                )
                for h in range(n_classes)
            ],
        )
        for node_id, node in result.nodes.items()
    ]
    return BestResponseOut(
        fingerprint=fingerprint,
        hero=cast(PositionName, result.hero.name),
        locked_nodes=list(result.locked_nodes),
        value=result.value,
        equilibrium_ev=result.equilibrium_ev,
        gain=result.gain,
        hands=hands,
        nodes=nodes,
        limitations=list(result.limitations),
    )


def best_response_params(fingerprint: str, hero: str, locks: dict[str, Any]) -> dict[str, Any]:
    """JSON parameters of a best-response job."""
    return {"fingerprint": fingerprint, "hero": hero, "locks": locks}


def run_best_response(
    jobs: JobStore, store: SolutionStore, equity: EquitySource, job_id: str
) -> None:
    """Entry point of the worker process: compute the job and record its outcome."""
    if not jobs.start(job_id):
        return
    try:
        job = jobs.get(job_id)
        if job is None:
            raise KeyError(f"job {job_id} disappeared")
        fingerprint: str = job.params["fingerprint"]
        solution = store.load(fingerprint)
        locks = {
            node_id: np.asarray(strategy, dtype=np.float64)
            for node_id, strategy in job.params["locks"].items()
        }
        result = exploit_solution(
            solution,
            _terminal_values(equity, fingerprint, solution),
            locks,
            Position[job.params["hero"]],
        )
        jobs.finish(
            job_id, best_response_out(solution, fingerprint, result).model_dump(mode="json")
        )
    except Exception as error:  # any failure belongs to the job, not to the worker
        jobs.fail(job_id, f"{type(error).__name__}: {error}")
