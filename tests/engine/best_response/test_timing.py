"""SC-005: a best response on the real library in less than 5 s (goal: 1 s with reused values).

Needs the equity tensors and the library (``engine batch``): skipped otherwise.
"""

import time
from pathlib import Path
from typing import Final

import pytest

from engine.best_response import exploit_solution
from engine.equity.storage import DEFAULT_DIRECTORY, load_tensors, read_manifest
from engine.game import Position
from engine.library import FileSolutionStore
from engine.solver import EquityTables, TerminalValues

ROOT: Final = Path(__file__).parents[3]
TENSORS: Final = ROOT / DEFAULT_DIRECTORY
STORE: Final = ROOT / "data" / "solutions"


def _available() -> bool:
    try:
        return read_manifest(TENSORS).classes is None and any(
            s.stacks[0] == 20.0 for s in FileSolutionStore(STORE).list_solutions()
        )
    except (FileNotFoundError, ValueError):
        return False


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _available(), reason="equity tensors or library missing"),
]


@pytest.mark.parametrize("stack", [20.0, 25.0])
def test_best_response_takes_less_than_five_seconds(stack: float) -> None:
    tables = EquityTables.from_stored(load_tensors(TENSORS))
    tables.digest  # noqa: B018 (computed once per tensor set, outside the request)
    store = FileSolutionStore(STORE)
    summary = next(s for s in store.list_solutions(publishable_only=True) if s.stacks[0] == stack)
    solution = store.load(summary.fingerprint)
    villain = next(n for n in solution.tree if n.actor is Position.BTN)

    start = time.perf_counter()
    values = TerminalValues(solution.tree, tables, solution.profile)
    lock = {villain.id: solution.strategy[villain.id]}
    exploit_solution(solution, values, lock, Position.SB)
    cold = time.perf_counter() - start

    start = time.perf_counter()
    exploit_solution(solution, values, lock, Position.BB)
    warm = time.perf_counter() - start

    assert cold < 5.0
    assert warm < 1.0
