"""Tests of saved villain strategies (FR-017, D-020): validation and reuse as a lock."""

import numpy as np
import pytest

from engine.best_response import (
    StrategyError,
    check_strategy,
    lock_from_saved,
    validate_saved,
)
from engine.cards import N_CLASSES, parse_class
from engine.game import ROOT_ID, GameConfig, build_tree


def pure(n_actions: int, action: int, n_classes: int = N_CLASSES) -> np.ndarray:
    """Every hand plays ``action``."""
    strategy = np.zeros((n_actions, n_classes))
    strategy[action] = 1.0
    return strategy


# --- check_strategy ----------------------------------------------------------------------


def test_a_valid_strategy_is_returned_as_floats() -> None:
    checked = check_strategy([[1, 0, 0.5], [0, 1, 0.5]], n_actions=2, n_classes=3)
    assert checked.dtype == np.float64
    assert checked.tolist() == [[1.0, 0.0, 0.5], [0.0, 1.0, 0.5]]


def test_wrong_shape_is_rejected() -> None:
    with pytest.raises(StrategyError, match="shape"):
        check_strategy(np.ones((3, 4)) / 3, n_actions=2, n_classes=4)


def test_ragged_rows_are_rejected() -> None:
    with pytest.raises(StrategyError, match="shape"):
        check_strategy([[1.0], [0.0, 1.0]], n_actions=2, n_classes=2)


def test_the_faulty_hands_are_named() -> None:
    """Spec edge case: an incomplete strategy is refused and its hands are reported."""
    strategy = pure(2, 0)
    aks, t9o, two = parse_class("AKs"), parse_class("T9o"), parse_class("22")
    strategy[0, aks] = 0.7  # sums to 0.7
    strategy[1, t9o] = 0.5  # sums to 1.5
    strategy[:, two] = [-0.5, 1.5]  # sums to 1 but negative
    with pytest.raises(StrategyError, match="probability") as raised:
        check_strategy(strategy, n_actions=2)
    assert set(raised.value.hands) == {"AKs", "T9o", "22"}
    assert "AKs" in str(raised.value)


def test_non_finite_frequencies_are_rejected() -> None:
    strategy = pure(2, 0)
    strategy[0, parse_class("AA")] = np.nan
    with pytest.raises(StrategyError) as raised:
        check_strategy(strategy, n_actions=2)
    assert raised.value.hands == ("AA",)


def test_the_label_prefixes_the_message() -> None:
    with pytest.raises(StrategyError, match=r"^lock of 'A' must have shape"):
        check_strategy(np.ones((1, 2)), n_actions=2, n_classes=2, label="lock of 'A'")


def test_strategy_error_is_a_value_error() -> None:
    assert issubclass(StrategyError, ValueError)


# --- validate_saved ----------------------------------------------------------------------


def test_a_saved_strategy_covers_the_169_classes() -> None:
    checked = validate_saved(["F", "R2.0"], pure(2, 1))
    assert checked.shape == (2, N_CLASSES)
    with pytest.raises(StrategyError, match="shape"):
        validate_saved(["F", "R2.0"], pure(2, 1, n_classes=4))


@pytest.mark.parametrize("actions", [[], ["F", "F"], ["F", ""]])
def test_saved_actions_must_be_distinct_labels(actions: list[str]) -> None:
    with pytest.raises(ValueError, match="action"):
        validate_saved(actions, pure(max(len(actions), 1), 0))


# --- lock_from_saved ---------------------------------------------------------------------


def test_a_saved_strategy_becomes_a_lock_on_a_node_with_the_same_actions() -> None:
    """A 15bb BTN open (F, C, R2.0, A) is reused at 12bb, which has the same actions."""
    tree = build_tree(GameConfig.equal_stacks(12.0))
    actions = [a.token for a in tree.node(ROOT_ID).actions]
    assert actions == ["F", "C", "R2.0", "A"]
    saved = pure(4, 2)
    lock = lock_from_saved(tree, ROOT_ID, actions, saved)
    np.testing.assert_array_equal(lock, saved)


def test_the_rows_follow_the_node_action_order() -> None:
    tree = build_tree(GameConfig.equal_stacks(12.0))
    saved = pure(4, 0)  # all in "A", listed first
    lock = lock_from_saved(tree, ROOT_ID, ["A", "F", "C", "R2.0"], saved)
    np.testing.assert_array_equal(lock, pure(4, 3))


def test_other_actions_are_refused_with_the_differences() -> None:
    """A 15bb open (with R2.0) does not apply at 5bb, where the BTN has F, C, A only."""
    tree = build_tree(GameConfig.equal_stacks(5.0))
    with pytest.raises(ValueError, match=r"R2\.0") as raised:
        lock_from_saved(tree, ROOT_ID, ["F", "C", "R2.0", "A"], pure(4, 0))
    assert "F, C, A" in str(raised.value)


def test_unknown_or_terminal_nodes_are_refused() -> None:
    tree = build_tree(GameConfig.equal_stacks(12.0))
    with pytest.raises(ValueError, match="unknown"):
        lock_from_saved(tree, "nope", ["F"], pure(1, 0))
    with pytest.raises(ValueError, match="terminal"):
        lock_from_saved(tree, "F-F", ["F"], pure(1, 0))


def test_an_invalid_saved_strategy_is_refused() -> None:
    tree = build_tree(GameConfig.equal_stacks(12.0))
    bad = pure(4, 0)
    bad[0, 0] = 0.0
    with pytest.raises(StrategyError):
        lock_from_saved(tree, ROOT_ID, ["F", "C", "R2.0", "A"], bad)
