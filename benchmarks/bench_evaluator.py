"""Throughput of the hand evaluators (7-card hands per second).

Run: ``uv run python benchmarks/bench_evaluator.py``
Results are recorded in ``benchmarks/README.md``.
"""

import platform
import time
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from engine.evaluator import evaluate, evaluate_batch

SEED = 20261126
N_FAST = 1_000_000
N_REFERENCE = 5_000
REPEATS = 5


def random_hands(n: int, rng: np.random.Generator) -> NDArray[np.int8]:
    """``n`` random 7-card hands with distinct cards in each row."""
    keys = rng.random((n, 52))
    return np.argpartition(keys, 7, axis=1)[:, :7].astype(np.int8)


def best_time(run: Callable[[], object]) -> float:
    """Best wall-clock time out of ``REPEATS`` runs."""
    timings = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        run()
        timings.append(time.perf_counter() - start)
    return min(timings)


def main() -> None:
    rng = np.random.default_rng(SEED)
    hands = random_hands(N_FAST, rng)
    sample = hands[:N_REFERENCE].tolist()

    evaluate_batch(hands[:1000])  # warm-up
    fast = best_time(lambda: evaluate_batch(hands))
    reference = best_time(lambda: [evaluate(hand) for hand in sample])

    print(f"Python {platform.python_version()}, NumPy {np.__version__}, {platform.processor()}")
    print(f"fast      : {N_FAST / fast:>13,.0f} hands/s ({N_FAST:,} hands, best of {REPEATS})")
    print(
        f"reference : {N_REFERENCE / reference:>13,.0f} hands/s "
        f"({N_REFERENCE:,} hands, best of {REPEATS})"
    )
    print(f"speed-up  : {reference / N_REFERENCE * N_FAST / fast:>13,.0f}x")


if __name__ == "__main__":
    main()
