"""Cost of one Discounted CFR iteration on the real 169-class tensors (issue #19).

Run: ``uv run python benchmarks/bench_cfr.py`` (needs ``data/equity``).
Results are recorded in ``benchmarks/README.md``.
"""

import platform
import time

import numpy as np

from engine.equity.storage import load_tensors
from engine.game import GameConfig, Position, build_tree
from engine.realization import default_profile
from engine.solver import DCFRSolver, EquityTables, TerminalValues

SEED = 20261127
STACKS = (8.0, 12.0, 20.0)
ITERATIONS = 5


def main() -> None:
    tables = EquityTables.from_stored(load_tensors(verify=False))
    rng = np.random.default_rng(SEED)
    for stack in STACKS:
        tree = build_tree(GameConfig.equal_stacks(stack))
        values = TerminalValues(tree, tables, default_profile())
        terminals = [node.id for node in tree if node.is_terminal]
        reaches = {node_id: tuple(rng.random(169) for _ in range(3)) for node_id in terminals}
        values.values_batch(Position.BTN, reaches)  # warm-up: flop cache

        start = time.perf_counter()
        for player in Position:
            for node_id in terminals:
                values.values(node_id, player, reaches[node_id])
        one_by_one = time.perf_counter() - start

        start = time.perf_counter()
        for player in Position:
            values.values_batch(player, reaches)
        batched = time.perf_counter() - start

        solver = DCFRSolver(tree, values)
        solver.iterate(1)  # warm-up
        start = time.perf_counter()
        solver.iterate(ITERATIONS)
        per_iteration = (time.perf_counter() - start) / ITERATIONS

        print(
            f"{stack:.0f}bb : {len(tree)} nœuds, {len(terminals)} terminaux | "
            f"terminaux x 3 joueurs : un par un {one_by_one:.2f} s, par lots {batched:.3f} s "
            f"(x{one_by_one / batched:.0f}) | itération DCFR : {per_iteration:.3f} s"
        )
    print(f"{platform.processor()} | Python {platform.python_version()} | NumPy {np.__version__}")


if __name__ == "__main__":
    main()
