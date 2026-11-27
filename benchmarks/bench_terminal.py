"""Cost of the terminal values on the real 169-class tensors (issue #18).

Run: ``uv run python benchmarks/bench_terminal.py`` (needs ``data/equity``).
Results are recorded in ``benchmarks/README.md``.
"""

import platform
import time
from collections.abc import Callable

import numpy as np

from engine.equity.storage import load_tensors
from engine.game import GameConfig, Position, TerminalKind, build_tree
from engine.realization import default_profile
from engine.solver import EquityTables, TerminalValues

SEED = 20261127
STACK = 20.0
REPEATS = 20
NODES = {
    "fold (R2.0-F-F)": "R2.0-F-F",
    "showdown 3 joueurs (A-C-C)": "A-C-C",
    "showdown 2 joueurs (A-F-C)": "A-F-C",
    "flop 2 joueurs (R2.0-F-C)": "R2.0-F-C",
    "flop 3 joueurs (C-C-X)": "C-C-X",
}


def best_time(run: Callable[[], object], repeats: int = REPEATS) -> float:
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        run()
        timings.append(time.perf_counter() - start)
    return min(timings)


def main() -> None:
    start = time.perf_counter()
    tables = EquityTables.from_stored(load_tensors(verify=False))
    print(
        f"Préparation des tables (float64, renormalisation) : {time.perf_counter() - start:.2f} s"
    )

    tree = build_tree(GameConfig.equal_stacks(STACK))
    values = TerminalValues(tree, tables, default_profile())
    rng = np.random.default_rng(SEED)
    reaches = tuple(rng.random(169) for _ in range(3))

    for label, node_id in NODES.items():
        values.values(node_id, Position.BTN, reaches)  # warm-up (flop cache)
        elapsed = best_time(lambda n=node_id: values.values(n, Position.BTN, reaches))
        print(f"{label:<30} {elapsed * 1e3:7.2f} ms par appel")

    terminals = [node for node in tree if node.is_terminal]
    start = time.perf_counter()
    for node in terminals:
        if node.terminal is TerminalKind.FLOP:
            values.values(node.id, Position.BTN, reaches)
    cache_build = time.perf_counter() - start

    def full_pass() -> None:
        for node in terminals:
            for player in Position:
                values.values(node.id, player, reaches)

    elapsed = best_time(full_pass, repeats=3)
    cached = values._flop_shares  # benchmark only: inspect the cache size
    n_tensors = sum(len(shares) for shares in cached.values())
    megabytes = n_tensors * tables.w.nbytes / 1e6
    print(f"Arbre {STACK:.0f}bb : {len(terminals)} terminaux, {len(cached)} contextes de flop")
    print(f"Construction du cache de flop : {cache_build:.2f} s")
    print(f"Cache de flop : {n_tensors} tenseurs, {megabytes:.0f} Mo")
    print(f"Passe complète (tous terminaux x 3 joueurs) : {elapsed:.2f} s")
    print(f"{platform.processor()} | Python {platform.python_version()} | NumPy {np.__version__}")


if __name__ == "__main__":
    main()
