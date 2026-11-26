"""Validation of the Monte-Carlo equities against exhaustive enumeration (SC-003, D-003)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from engine.equity.exact import three_way_equity
from engine.equity.montecarlo import estimate_sorted_triplets, feasible_sorted_triplets

D003_MEAN_POINTS: Final = 0.1
"""D-003: mean absolute error of the three-way equities, in percentage points."""
D003_MAX_POINTS: Final = 0.3
"""D-003: maximum absolute error of the three-way equities, in percentage points."""


@dataclass(frozen=True)
class ValidationReport:
    """Errors (Monte-Carlo - exact) in percentage points, per triplet and player or pair."""

    n_triplets: int
    n_draws: int
    seed: int
    triplets: NDArray[np.int64]
    e3_errors: NDArray[np.float64]
    e2_errors: NDArray[np.float64]

    @property
    def e3_mean(self) -> float:
        return float(np.abs(self.e3_errors).mean())

    @property
    def e3_max(self) -> float:
        return float(np.abs(self.e3_errors).max())

    @property
    def e2_mean(self) -> float:
        return float(np.abs(self.e2_errors).mean())

    @property
    def e2_max(self) -> float:
        return float(np.abs(self.e2_errors).max())

    @property
    def passes(self) -> bool:
        """Whether the three-way equities meet D-003."""
        return self.e3_mean < D003_MEAN_POINTS and self.e3_max < D003_MAX_POINTS


def validate_against_exact(
    n_triplets: int,
    n_draws: int,
    seed: int,
    progress: Callable[[int, int], None] | None = None,
) -> ValidationReport:
    """Compare Monte-Carlo and exact equities on random distinct feasible sorted triplets.

    The triplets are drawn with ``seed``; the Monte-Carlo values use the same
    per-triplet seeds as :func:`compute_equity_tensors` with that ``seed``.
    """
    if n_triplets <= 0 or n_draws <= 0:
        raise ValueError("n_triplets and n_draws must be positive")
    candidates = feasible_sorted_triplets()
    rng = np.random.default_rng(seed)
    picked = np.sort(rng.choice(len(candidates), size=n_triplets, replace=False))
    triplets = candidates[picked]

    estimates = estimate_sorted_triplets(triplets, n_draws, seed)
    exact = np.empty_like(estimates)
    for row, (a, b, c) in enumerate(triplets.tolist()):
        result = three_way_equity(a, b, c)
        exact[row] = (*result.three_way, *result.heads_up)
        if progress is not None:
            progress(row + 1, n_triplets)
    errors = (estimates - exact) * 100
    return ValidationReport(
        n_triplets=n_triplets,
        n_draws=n_draws,
        seed=seed,
        triplets=triplets,
        e3_errors=errors[:, :3],
        e2_errors=errors[:, 3:],
    )
