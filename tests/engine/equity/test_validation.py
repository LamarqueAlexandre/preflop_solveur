"""Tests for the validation of the Monte-Carlo equities against the exact ones (D-003)."""

import numpy as np
import pytest

from engine.equity import (
    D003_MAX_POINTS,
    D003_MEAN_POINTS,
    ValidationReport,
    validate_against_exact,
)


@pytest.fixture(scope="module")
def report() -> ValidationReport:
    return validate_against_exact(n_triplets=6, n_draws=200_000, seed=20261126)


def test_thresholds_are_those_of_d003() -> None:
    assert D003_MEAN_POINTS == 0.1
    assert D003_MAX_POINTS == 0.3


def test_report_shapes(report: ValidationReport) -> None:
    assert report.n_triplets == 6
    assert report.n_draws == 200_000
    assert report.triplets.shape == (6, 3)
    assert report.e3_errors.shape == report.e2_errors.shape == (6, 3)


def test_report_statistics_are_consistent(report: ValidationReport) -> None:
    assert report.e3_mean == pytest.approx(np.abs(report.e3_errors).mean())
    assert report.e3_max == pytest.approx(np.abs(report.e3_errors).max())
    assert report.e2_mean == pytest.approx(np.abs(report.e2_errors).mean())
    assert report.e2_max == pytest.approx(np.abs(report.e2_errors).max())
    assert 0 <= report.e3_mean <= report.e3_max


def test_triplets_are_sorted_distinct_and_feasible(report: ValidationReport) -> None:
    assert np.all(np.diff(report.triplets, axis=1) >= 0)
    assert len({tuple(t) for t in report.triplets.tolist()}) == 6


def test_small_sample_meets_d003(report: ValidationReport) -> None:
    # Errors are in percentage points; 200 000 draws keep them well below the thresholds.
    assert report.e3_mean < D003_MEAN_POINTS
    assert report.e3_max < D003_MAX_POINTS
    assert report.passes


def test_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        validate_against_exact(n_triplets=0, n_draws=1000, seed=1)
    with pytest.raises(ValueError):
        validate_against_exact(n_triplets=3, n_draws=0, seed=1)
