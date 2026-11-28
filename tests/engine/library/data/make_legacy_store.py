"""Write ``legacy_store/``: a solution of "engine version 0.0.0", store format 1.

Run once to freeze the fixture (``uv run python tests/engine/library/data/make_legacy_store.py``).
Never rerun it to make a test pass: the point of the fixture is that it does
not change when the engine does (test_store.py, D-016).
"""

from dataclasses import replace
from pathlib import Path

import numpy as np

from engine.game import GameConfig, build_tree
from engine.library import FileSolutionStore, SolveParams, solve
from engine.realization import default_profile
from engine.solver import EquityTables

TARGET = Path(__file__).parent / "legacy_store"


def main() -> None:
    s = np.array([3.0, 1.0, 2.0, 0.7])
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    tables = EquityTables.from_arrays(
        np.ones((n, n, n)),
        np.broadcast_to(a / (a + b + c), (n, n, n)).copy(),
        np.broadcast_to(a / (a + b), (n, n, n)).copy(),
    )
    tree = build_tree(GameConfig.equal_stacks(5.0))
    solution = solve(
        tree, tables, default_profile(), SolveParams(max_iterations=50, check_every=10)
    )
    store = FileSolutionStore(TARGET)
    store.save(replace(solution, engine_version="0.0.0"))
    (TARGET / "index.sqlite").unlink()  # a cache, rebuilt by the tests


if __name__ == "__main__":
    main()
