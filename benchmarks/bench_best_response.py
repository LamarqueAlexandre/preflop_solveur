"""Best response against locked villains on the real library (SC-005, issue #27).

Run: ``uv run python benchmarks/bench_best_response.py`` (needs ``data/equity`` and the
library in ``data/solutions``, see ``engine batch``).

For 5, 12, 20 and 25bb: hero SB, the BTN root locked to its equilibrium (a lock
that changes nothing) or to its largest action below all-in with every hand.
"Cold" includes building the terminal values of the solution (flop-share cache);
"warm" reuses them. Each time is the best of 3 runs (1 for cold).
Results are recorded in ``benchmarks/README.md``.
"""

import time
from typing import Final

import numpy as np

from engine.best_response import exploit_solution
from engine.equity.storage import load_tensors
from engine.game import ROOT_ID, Position
from engine.library import FileSolutionStore, Solution
from engine.solver import EquityTables, TerminalValues

STACKS: Final = (5.0, 12.0, 20.0, 25.0)


def enter_everything(solution: Solution) -> tuple[str, dict[str, np.ndarray]]:
    """BTN plays, with every hand, its largest action below all-in at the root."""
    root = solution.tree.root
    action = max(len(root.actions) - 2, 1)
    played = np.zeros((len(root.actions), solution.hand_mass.shape[0]))
    played[action] = 1.0
    return f"{root.actions[action].token} 100 %", {ROOT_ID: played}


def main() -> None:
    tables = EquityTables.from_stored(load_tensors(verify=False))
    tables.digest  # noqa: B018 (once per tensor set)
    store = FileSolutionStore("data/solutions")
    summaries = {s.stacks[0]: s for s in store.list_solutions(publishable_only=True)}
    for stack in STACKS:
        solution = store.load(summaries[stack].fingerprint)
        for label, locks in (
            ("équilibre", {ROOT_ID: solution.strategy[ROOT_ID]}),
            enter_everything(solution),
        ):
            start = time.perf_counter()
            values = TerminalValues(solution.tree, tables, solution.profile)
            result = exploit_solution(solution, values, locks, Position.SB)
            cold = time.perf_counter() - start
            warm = float("inf")
            for _ in range(3):
                start = time.perf_counter()
                exploit_solution(solution, values, locks, Position.SB)
                warm = min(warm, time.perf_counter() - start)
            print(
                f"{stack:g}bb | BTN {label:<10} | à froid {cold:5.2f} s | à chaud {warm:5.3f} s "
                f"| EV gagnée SB {result.gain:+.4f} bb/main",
                flush=True,
            )


if __name__ == "__main__":
    main()
