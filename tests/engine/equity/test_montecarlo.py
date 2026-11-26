"""Tests for the Monte-Carlo equity tensors E3 and E2."""

from functools import cache

import numba
import numpy as np
import pytest

from engine.cards import N_CLASSES, parse_class
from engine.equity import (
    EquityTensors,
    compute_equity_tensors,
    estimate_three_way,
    three_way_equity,
)

SEED = 20261126
SUBSET = ("AA", "KK", "AKs", "72o", "22", "T9s")


def classes(*names: str) -> tuple[int, ...]:
    return tuple(parse_class(name) for name in names)


@cache
def subset_tensors() -> EquityTensors:
    return compute_equity_tensors(n_draws=20_000, seed=SEED, classes=classes(*SUBSET))


# --- Single triplet ------------------------------------------------------------------


@pytest.mark.parametrize("names", [("AA", "KQs", "76s"), ("AKo", "22", "T9s"), ("AA", "AKs", "KK")])
def test_estimate_is_close_to_exact(names: tuple[str, str, str]) -> None:
    n = 200_000
    estimate = estimate_three_way(*classes(*names), n_draws=n, seed=SEED)
    exact = three_way_equity(*classes(*names))
    tolerance = 5 * 0.5 / np.sqrt(n)  # five standard errors
    np.testing.assert_allclose(estimate.three_way, exact.three_way, atol=tolerance)
    np.testing.assert_allclose(estimate.heads_up, exact.heads_up, atol=tolerance)


def test_same_seed_gives_identical_estimates() -> None:
    triplet = classes("AKo", "22", "T9s")
    first = estimate_three_way(*triplet, n_draws=10_000, seed=SEED)
    second = estimate_three_way(*triplet, n_draws=10_000, seed=SEED)
    assert first == second


def test_other_seed_gives_other_estimates() -> None:
    triplet = classes("AKo", "22", "T9s")
    first = estimate_three_way(*triplet, n_draws=10_000, seed=SEED)
    second = estimate_three_way(*triplet, n_draws=10_000, seed=SEED + 1)
    assert first != second


def test_estimate_does_not_depend_on_player_order() -> None:
    # Players reordered as (T9s, AKo, 22): the very same draws, permuted.
    first = estimate_three_way(*classes("AKo", "22", "T9s"), n_draws=10_000, seed=SEED)
    second = estimate_three_way(*classes("T9s", "AKo", "22"), n_draws=10_000, seed=SEED)
    assert second.three_way == (first.three_way[2], first.three_way[0], first.three_way[1])
    assert second.heads_up == pytest.approx(
        (1 - first.heads_up[1], 1 - first.heads_up[2], first.heads_up[0]), abs=1e-12
    )


def test_estimate_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        estimate_three_way(*classes("AA", "AA", "AA"), n_draws=1000, seed=SEED)
    with pytest.raises(ValueError):
        estimate_three_way(0, 1, N_CLASSES, n_draws=1000, seed=SEED)
    with pytest.raises(ValueError):
        estimate_three_way(*classes("AA", "KK", "QQ"), n_draws=0, seed=SEED)


# --- Tensors -----------------------------------------------------------------------


def test_tensor_shape_dtype_and_metadata() -> None:
    tensors = subset_tensors()
    assert tensors.e3.shape == tensors.e2.shape == (N_CLASSES, N_CLASSES, N_CLASSES)
    assert tensors.e3.dtype == tensors.e2.dtype == np.float32
    assert tensors.n_draws == 20_000
    assert tensors.seed == SEED


def test_cells_outside_the_subset_or_impossible_are_nan() -> None:
    tensors = subset_tensors()
    aa, kk, qq = classes("AA", "KK", "QQ")
    assert np.isnan(tensors.e3[aa, aa, aa])
    assert np.isnan(tensors.e2[aa, aa, aa])
    assert np.isnan(tensors.e3[aa, kk, qq])  # QQ is not in the subset
    filled = ~np.isnan(tensors.e3)
    assert filled.sum() == np.sum(~np.isnan(tensors.e2))
    assert filled.sum() > 0


def test_three_way_symmetries() -> None:
    e3 = subset_tensors().e3
    idx = list(classes(*SUBSET))
    sub = e3[np.ix_(idx, idx, idx)]
    feasible = ~np.isnan(sub)
    # Player a facing b and c does not care about the order of b and c.
    np.testing.assert_array_equal(sub[feasible], sub.transpose(0, 2, 1)[feasible])
    # The three players' shares sum to one.
    total = sub + sub.transpose(1, 0, 2) + sub.transpose(1, 2, 0)
    np.testing.assert_allclose(total[feasible], 1.0, atol=1e-6)


def test_heads_up_symmetries() -> None:
    e2 = subset_tensors().e2
    idx = list(classes(*SUBSET))
    sub = e2[np.ix_(idx, idx, idx)]
    feasible = ~np.isnan(sub)
    np.testing.assert_allclose((sub + sub.transpose(1, 0, 2))[feasible], 1.0, atol=1e-6)


def test_identical_classes_are_exactly_symmetric() -> None:
    tensors = subset_tensors()
    kk, seven_deuce, ten_nine = classes("KK", "72o", "T9s")
    assert tensors.e2[kk, kk, seven_deuce] == pytest.approx(0.5, abs=1e-7)
    # Three T9s in three different suits.
    assert tensors.e3[ten_nine, ten_nine, ten_nine] == pytest.approx(1 / 3, abs=1e-7)
    assert tensors.e2[ten_nine, ten_nine, ten_nine] == pytest.approx(0.5, abs=1e-7)


def test_tensor_values_match_single_estimates() -> None:
    tensors = subset_tensors()
    a, b, c = classes("AKs", "72o", "T9s")
    single = estimate_three_way(a, b, c, n_draws=20_000, seed=SEED)
    assert tensors.e3[a, b, c] == pytest.approx(single.three_way[0], abs=1e-7)
    assert tensors.e3[b, a, c] == pytest.approx(single.three_way[1], abs=1e-7)
    assert tensors.e3[c, a, b] == pytest.approx(single.three_way[2], abs=1e-7)
    assert tensors.e2[a, b, c] == pytest.approx(single.heads_up[0], abs=1e-7)
    assert tensors.e2[a, c, b] == pytest.approx(single.heads_up[1], abs=1e-7)
    assert tensors.e2[b, c, a] == pytest.approx(single.heads_up[2], abs=1e-7)


def test_result_does_not_depend_on_thread_count() -> None:
    subset = classes("AA", "AKs", "72o", "T9s")
    threads = numba.get_num_threads()
    try:
        numba.set_num_threads(1)
        single = compute_equity_tensors(n_draws=5_000, seed=SEED, classes=subset)
    finally:
        numba.set_num_threads(threads)
    parallel = compute_equity_tensors(n_draws=5_000, seed=SEED, classes=subset)
    np.testing.assert_array_equal(single.e3, parallel.e3)
    np.testing.assert_array_equal(single.e2, parallel.e2)


def test_progress_is_reported() -> None:
    calls: list[tuple[int, int]] = []
    compute_equity_tensors(
        n_draws=1_000,
        seed=SEED,
        classes=classes("AA", "KK", "AKs"),
        progress=lambda done, total: calls.append((done, total)),
        batch_size=3,
    )
    assert len(calls) >= 2
    assert calls[-1][0] == calls[-1][1]
    assert [done for done, _ in calls] == sorted(done for done, _ in calls)


def test_tensors_reject_invalid_input() -> None:
    with pytest.raises(ValueError):
        compute_equity_tensors(n_draws=0, seed=SEED, classes=classes("AA", "KK"))
    with pytest.raises(ValueError):
        compute_equity_tensors(n_draws=100, seed=SEED, classes=(0, N_CLASSES))
