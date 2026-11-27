"""Tests for the independent fictitious play on the 3-max push/fold game (SC-002.2, D-004).

Synthetic tables: classes with a "strength" s, the share of a hand in a pot is
s / (sum of the strengths of the hands in the pot). With W = 1 everywhere,
every triplet of classes is equally likely and the expectations below are
computed by hand.

Two classes, STRONG (3) and WEAK (1), stack 10bb. Heads-up shares: 1/2 between
equals, 3/4 for STRONG against WEAK; averaged over the opponent's class, each
class has 5/8 (STRONG) or 3/8 (WEAK), and the mean share is 1/2.
"""

import numpy as np
import pytest
from numpy.typing import NDArray

from engine.reference import DECISION_NODES, PushFoldFictitiousPlay

STRONG, WEAK = 0, 1
STACK = 10.0
Tables = tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]


def strength_tables(strengths: list[float]) -> Tables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return np.ones((n, n, n)), e3, e2


def solver(stack: float = STACK) -> PushFoldFictitiousPlay:
    return PushFoldFictitiousPlay(*strength_tables([3.0, 1.0]), stack=stack)


def profile(**aggressive: list[float]) -> dict[str, NDArray[np.float64]]:
    """Probability of the aggressive action (push or call) by node; 0 when not given."""
    names = {"root": "root", "F": "F", "FA": "F-A", "A": "A", "AF": "A-F", "AC": "A-C"}
    result = {node: np.zeros(2) for node in DECISION_NODES}
    for name, values in aggressive.items():
        result[names[name]] = np.asarray(values, dtype=np.float64)
    return result


# --- Game and payoffs ----------------------------------------------------------------------


def test_decision_nodes_are_those_of_the_push_fold_tree() -> None:
    assert DECISION_NODES == ("root", "F", "F-A", "A", "A-F", "A-C")


def test_everyone_folds_to_the_bb() -> None:
    assert solver().expected_values(profile()) == pytest.approx((0.0, -0.5, 0.5))


def test_sb_push_folded_by_the_bb() -> None:
    values = solver().expected_values(profile(F=[1, 1]))
    assert values == pytest.approx((0.0, 1.0, -1.0))


def test_btn_push_called_by_the_bb_only() -> None:
    """Pot 2S + 0.5 with the SB's dead blind, mean share 1/2: BTN and BB win 0.25 each."""
    values = solver().expected_values(profile(root=[1, 1], AF=[1, 1]))
    assert values == pytest.approx((0.25, -0.5, 0.25))


def test_three_way_all_in_with_one_strong_hand() -> None:
    """Pot 3S, all-in for everyone: shares s_i / (s_btn + s_sb + s_bb), averaged by hand."""
    tables = strength_tables([3.0, 1.0])
    values = PushFoldFictitiousPlay(*tables, stack=STACK).expected_values(
        profile(root=[1, 1], A=[1, 1], AC=[1, 1])
    )
    assert values == pytest.approx((0.0, 0.0, 0.0))


def test_only_strong_btn_pushes_and_the_sb_calls() -> None:
    """BTN pushes STRONG only (1/2 of the time); SB calls all, BB folds.

    BTN folds: SB and BB blinds, BB wins 0.5. BTN pushes: pot 2S + 1, BTN
    (STRONG) has 5/8 against the SB, so BTN = 21 * 5/8 - 10 = 3.125, SB =
    21 * 3/8 - 10 = -2.125, BB = -1.
    """
    values = solver().expected_values(profile(root=[1, 0], A=[1, 1]))
    assert values == pytest.approx((3.125 / 2, (-0.5 - 2.125) / 2, (0.5 - 1.0) / 2))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_payoffs_are_zero_sum(seed: int) -> None:
    rng = np.random.default_rng(seed)
    w, e3, e2 = strength_tables([4.0, 2.5, 1.0])
    random_profile = {node: rng.random(3) for node in DECISION_NODES}
    values = PushFoldFictitiousPlay(w, e3, e2, stack=7.0).expected_values(random_profile)
    assert sum(values) == pytest.approx(0.0, abs=1e-12)


def test_impossible_triplets_are_ignored() -> None:
    """W = 0 (card removal) on a triplet: its equities, even NaN, never count."""
    w, e3, e2 = strength_tables([3.0, 1.0])
    w[STRONG, STRONG, STRONG] = 0.0
    e3[STRONG, STRONG, STRONG] = np.nan
    e2[STRONG, STRONG, STRONG] = np.nan
    game = PushFoldFictitiousPlay(w, e3, e2, stack=STACK)
    values = game.expected_values(profile(root=[1, 1], A=[1, 1], AC=[1, 1]))
    assert np.isfinite(values).all()
    assert sum(values) == pytest.approx(0.0, abs=1e-12)


# --- Best response -------------------------------------------------------------------------


def test_bb_calls_a_strong_only_push_with_strong_only() -> None:
    """Facing a STRONG push, SB folded: calling wins 20.5 * 1/2 - 10 = 0.25 with STRONG
    and 20.5 * 1/4 - 10 = -4.875 with WEAK, folding loses 1."""
    best = solver().best_response(profile(root=[1, 0]))
    assert best["A-F"] == pytest.approx([1.0, 0.0])


def test_best_response_is_pure_where_values_differ() -> None:
    best = solver().best_response(profile(root=[0.5, 0.5], A=[0.5, 0.5]))
    for node in DECISION_NODES:
        assert set(np.unique(best[node])) <= {0.0, 0.5, 1.0}
    assert best["root"][STRONG] == 1.0


def test_best_response_never_loses_against_the_profile() -> None:
    game = solver()
    start = profile(root=[0.3, 0.6], F=[0.5, 0.5], A=[0.2, 0.9])
    assert game.nash_conv(start) > 0
    best = game.best_response(start)
    for player in range(3):
        mixed = dict(start)
        for node in game.nodes_of(player):
            mixed[node] = best[node]
        assert game.expected_values(mixed)[player] >= game.expected_values(start)[player] - 1e-12


# --- Fictitious play -----------------------------------------------------------------------


def test_starts_from_the_uniform_strategy() -> None:
    game = solver()
    assert game.iterations == 0
    for node in DECISION_NODES:
        assert game.average_strategy()[node] == pytest.approx([0.5, 0.5])


def test_average_moves_by_one_over_t_plus_one() -> None:
    """After one iteration the average is (uniform + best response to uniform) / 2."""
    game = solver()
    best = game.best_response(game.average_strategy())
    game.iterate(1)
    for node in DECISION_NODES:
        assert game.average_strategy()[node] == pytest.approx((0.5 + best[node]) / 2)


def test_exploitability_vanishes() -> None:
    game = solver()
    game.iterate(10)
    early = game.nash_conv(game.average_strategy())
    game.iterate(2000)
    late = game.nash_conv(game.average_strategy())
    assert late < early
    assert late / 1.5 < 0.005  # D-001: below 0.5% of the starting pot


def test_strong_hand_always_pushes_at_equilibrium() -> None:
    game = solver()
    game.iterate(2000)
    strategy = game.average_strategy()
    for node in DECISION_NODES:
        assert strategy[node][STRONG] == pytest.approx(1.0, abs=1e-2)


# --- Inputs --------------------------------------------------------------------------------


@pytest.mark.parametrize("stack", [1.0, 0.5])
def test_stack_must_cover_more_than_the_big_blind(stack: float) -> None:
    with pytest.raises(ValueError, match="stack"):
        solver(stack)


def test_tables_must_share_a_cubic_shape() -> None:
    w, e3, _ = strength_tables([3.0, 1.0])
    with pytest.raises(ValueError, match="shape"):
        PushFoldFictitiousPlay(w, e3, np.ones((2, 2)), stack=STACK)


def test_profile_must_cover_every_decision_node() -> None:
    partial = profile()
    del partial["A-C"]
    with pytest.raises(ValueError, match="A-C"):
        solver().expected_values(partial)
