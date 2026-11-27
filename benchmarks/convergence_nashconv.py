"""NashConv of the DCFR average strategy along the iterations, on the real tensors (#20).

Run: ``uv run python benchmarks/convergence_nashconv.py`` (needs ``data/equity``).
Results are recorded in ``benchmarks/README.md``.
"""

import platform
import sys
import time

import numpy as np

from engine.equity.storage import load_tensors
from engine.game import GameConfig, build_tree
from engine.realization import default_profile
from engine.solver import DCFRSolver, EquityTables, TerminalValues, exploitability

STACKS = (8.0, 12.0, 20.0)
CHECKPOINTS = (50, 100, 200, 500, 1000)


def main() -> None:
    tables = EquityTables.from_stored(load_tensors(verify=False))
    for stack in STACKS:
        tree = build_tree(GameConfig.equal_stacks(stack))
        values = TerminalValues(tree, tables, default_profile())
        solver = DCFRSolver(tree, values)
        solving = 0.0
        for checkpoint in CHECKPOINTS:
            start = time.perf_counter()
            solver.iterate(checkpoint - solver.iterations)
            solving += time.perf_counter() - start
            start = time.perf_counter()
            result = exploitability(tree, values, solver.average_strategy())
            measuring = time.perf_counter() - start
            print(
                f"{stack:.0f}bb | {checkpoint:5d} itérations | NashConv {result.percent:8.4f} % "
                f"du pot | gains {tuple(round(g, 5) for g in result.gains)} bb | "
                f"résolution {solving:6.1f} s | mesure {measuring:.2f} s",
                flush=True,
            )
    print(f"{platform.processor()} | Python {platform.python_version()} | NumPy {np.__version__}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
