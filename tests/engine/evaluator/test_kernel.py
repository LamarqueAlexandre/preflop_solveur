"""Tests for the Numba evaluator kernel: it must match evaluate_batch exactly."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.evaluator import evaluate_batch, evaluate_batch_numba


@settings(max_examples=1000, deadline=None)
@given(st.lists(st.integers(0, 51), min_size=5, max_size=7, unique=True))
def test_random_hands_match_evaluate_batch(hand: list[int]) -> None:
    batch = np.array([hand])
    assert evaluate_batch_numba(batch).tolist() == evaluate_batch(batch).tolist()


def test_random_seven_card_batch_matches_evaluate_batch() -> None:
    rng = np.random.default_rng(20261126)
    batch = np.argpartition(rng.random((100_000, 52)), 7, axis=1)[:, :7]
    result = evaluate_batch_numba(batch)
    assert result.dtype == np.int32
    np.testing.assert_array_equal(result, evaluate_batch(batch))


def test_empty_batch() -> None:
    assert evaluate_batch_numba(np.empty((0, 7), dtype=np.int64)).shape == (0,)


@pytest.mark.parametrize("shape", [(7,), (3, 4), (3, 8)])
def test_rejects_bad_shapes(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        evaluate_batch_numba(np.zeros(shape, dtype=np.int64))


@pytest.mark.parametrize("bad_card", [-1, 52])
def test_rejects_out_of_range_cards(bad_card: int) -> None:
    with pytest.raises(ValueError):
        evaluate_batch_numba(np.array([[0, 5, 10, 15, 20, 25, bad_card]]))
