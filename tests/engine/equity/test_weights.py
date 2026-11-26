"""Tests for W: number of card-disjoint combo triplets per ordered class triplet."""

from functools import cache
from itertools import permutations, product

import numpy as np
import pytest
from numpy.typing import NDArray

from engine.cards import CLASS_WEIGHTS, COMBOS, N_CLASSES, combos_of_class, parse_class
from engine.equity import compute_weights


@cache
def weights() -> NDArray[np.int32]:
    """W is computed once for the whole module."""
    return compute_weights()


def w(h1: str, h2: str, h3: str) -> int:
    return int(weights()[parse_class(h1), parse_class(h2), parse_class(h3)])


def brute_force(h1: int, h2: int, h3: int) -> int:
    """Independent reference: try every combo triplet and keep card-disjoint ones."""
    hands = [[set(COMBOS[c].tolist()) for c in combos_of_class(h)] for h in (h1, h2, h3)]
    return sum(
        1 for a, b, c in product(*hands) if a.isdisjoint(b) and a.isdisjoint(c) and b.isdisjoint(c)
    )


# --- Shape and type ----------------------------------------------------------------


def test_shape_and_dtype() -> None:
    assert weights().shape == (N_CLASSES, N_CLASSES, N_CLASSES)
    assert weights().dtype == np.int32


# --- Hand-computed cases -----------------------------------------------------------


@pytest.mark.parametrize(
    ("h1", "h2", "h3", "expected"),
    [
        # Only four aces: three pairs of aces are impossible.
        ("AA", "AA", "AA", 0),
        # 6 pairs of aces, then the single pair made of the 2 aces left, then 6 pairs of kings.
        ("AA", "AA", "KK", 6 * 1 * 6),
        # No shared rank: no card removal at all.
        ("AA", "KK", "QQ", 6 * 6 * 6),
        ("72o", "AA", "KK", 12 * 6 * 6),
        # AKs takes one ace and one king: 3 aces and 3 kings left.
        ("AKs", "AA", "KK", 4 * 3 * 3),
        ("AKo", "AA", "KK", 12 * 3 * 3),
        # Each AKs uses one suit: 4 * 3 * 2 ways to give three different suits.
        ("AKs", "AKs", "AKs", 4 * 3 * 2),
        # AKs in suit s; AKo needs an ace and a king of two other, different suits: 3 * 2.
        ("AKs", "AKo", "QQ", 4 * (3 * 2) * 6),
    ],
)
def test_hand_computed_cases(h1: str, h2: str, h3: str, expected: int) -> None:
    assert w(h1, h2, h3) == expected


# --- Global properties -----------------------------------------------------------------


def test_invariant_under_permutation_of_the_three_classes() -> None:
    table = weights()
    for axes in permutations(range(3)):
        np.testing.assert_array_equal(table.transpose(axes), table)


def test_total_is_the_number_of_disjoint_ordered_combo_triplets() -> None:
    # 1326 combos for the first player, then C(50, 2) and C(48, 2).
    assert int(weights().sum(dtype=np.int64)) == 1326 * 1225 * 1128 == 1_832_266_800


def test_bounded_by_the_product_of_class_sizes() -> None:
    table = weights().astype(np.int64)
    sizes = CLASS_WEIGHTS.astype(np.int64)
    upper = sizes[:, None, None] * sizes[None, :, None] * sizes[None, None, :]
    assert table.min() >= 0
    assert np.all(table <= upper)


# --- Against the brute-force reference ---------------------------------------------


def test_matches_brute_force_on_random_triplets() -> None:
    rng = np.random.default_rng(20261126)
    for h1, h2, h3 in rng.integers(N_CLASSES, size=(300, 3)).tolist():
        assert weights()[h1, h2, h3] == brute_force(h1, h2, h3), (h1, h2, h3)


def test_matches_brute_force_on_all_triplets_of_a_small_group() -> None:
    group = [parse_class(c) for c in ("AA", "KK", "AKs", "AKo", "A2s", "K2o", "72o", "22")]
    for h1, h2, h3 in product(group, repeat=3):
        assert weights()[h1, h2, h3] == brute_force(h1, h2, h3), (h1, h2, h3)
