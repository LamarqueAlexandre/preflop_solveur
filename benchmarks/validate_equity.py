"""D-003 validation: Monte-Carlo equities vs exhaustive enumeration on 1000 triplets.

Run: ``uv run python benchmarks/validate_equity.py``
Results are recorded in ``docs/notes/validation-equites.md``.
"""

import platform
import time

import numba
import numpy as np

from engine.cards import format_class
from engine.equity import (
    D003_MAX_POINTS,
    D003_MEAN_POINTS,
    N_DRAWS,
    validate_against_exact,
)

SEED = 20261126
N_TRIPLETS = 1000


def describe(label: str, errors: np.ndarray) -> None:
    absolute = np.abs(errors).ravel()
    quantiles = np.quantile(absolute, [0.5, 0.9, 0.99])
    print(
        f"  {label}: mean {absolute.mean():.4f}, median {quantiles[0]:.4f}, "
        f"p90 {quantiles[1]:.4f}, p99 {quantiles[2]:.4f}, max {absolute.max():.4f} "
        f"(points, {absolute.size} values)"
    )
    edges = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, np.inf]
    counts, _ = np.histogram(absolute, bins=edges)
    for low, high, count in zip(edges[:-1], edges[1:], counts, strict=True):
        print(f"    [{low:.2f}, {high:.2f}) : {count:>5}")


def main() -> None:
    print(f"Python {platform.python_version()}, NumPy {np.__version__}, Numba {numba.__version__}")
    print(f"{platform.processor()}, {numba.get_num_threads()} threads")
    print(f"{N_TRIPLETS} triplets, {N_DRAWS:,} draws each, seed {SEED}")
    start = time.perf_counter()

    def progress(done: int, total: int) -> None:
        if done % 100 == 0:
            print(f"  exact reference: {done}/{total} ({time.perf_counter() - start:.0f} s)")

    report = validate_against_exact(N_TRIPLETS, N_DRAWS, SEED, progress=progress)
    print(f"\ntotal time: {time.perf_counter() - start:.0f} s\n")
    describe("E3", report.e3_errors)
    describe("E2", report.e2_errors)

    worst = np.argsort(np.abs(report.e3_errors).max(axis=1))[::-1][:5]
    print("\n  worst E3 triplets:")
    for row in worst:
        names = " / ".join(format_class(int(c)) for c in report.triplets[row])
        print(f"    {names:<18} errors {np.round(report.e3_errors[row], 4)}")

    print(
        f"\nD-003 (E3): mean {report.e3_mean:.4f} < {D003_MEAN_POINTS} and "
        f"max {report.e3_max:.4f} < {D003_MAX_POINTS} -> {'PASS' if report.passes else 'FAIL'}"
    )


if __name__ == "__main__":
    main()
