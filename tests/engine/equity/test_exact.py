"""Tests for the exhaustive (exact) equities between classes and between combos."""

from itertools import combinations

import numpy as np
import pytest

from engine.cards import parse_card, parse_class
from engine.equity import (
    PAIRS,
    compute_weights,
    exact_combo_equity,
    heads_up_equity,
    suit_configurations,
    three_way_equity,
)
from engine.evaluator import evaluate, evaluate_batch


def cards(text: str) -> list[int]:
    return [parse_card(token) for token in text.split()]


def classes(*names: str) -> tuple[int, ...]:
    return tuple(parse_class(name) for name in names)


# --- Suit configurations -----------------------------------------------------------


@pytest.mark.parametrize(
    "names",
    [("AA", "KK", "QQ"), ("AKs", "AA", "KK"), ("AKo", "22", "T9s"), ("72o", "A2s", "K7o")],
)
def test_configuration_weights_sum_to_w(names: tuple[str, ...]) -> None:
    triplet = classes(*names)
    _, weights = suit_configurations(triplet)
    assert int(weights.sum()) == int(compute_weights()[triplet])


def test_aa_aks_kk_has_two_configurations() -> None:
    # The AKs suit matches one of the two missing aces... or not: 2 cases.
    representatives, weights = suit_configurations(classes("AA", "AKs", "KK"))
    assert representatives.shape == (2, 6)
    assert sorted(weights.tolist()) == [12, 24]


def test_aa_vs_kk_configurations() -> None:
    # Suits shared between the two pairs: 0, 1 or 2.
    representatives, weights = suit_configurations(classes("AA", "KK"))
    assert representatives.shape == (3, 4)
    assert sorted(weights.tolist()) == [6, 6, 24]


def test_infeasible_triplet_has_no_configuration() -> None:
    representatives, weights = suit_configurations(classes("AA", "AA", "AA"))
    assert len(representatives) == 0
    assert len(weights) == 0


# --- Combo equity with a partial board, against the naive reference -------------------


def naive_equity(hands: list[list[int]], board: list[int]) -> list[float]:
    """Exact pot shares by enumerating every completion with the naive evaluator."""
    used = {card for hand in hands for card in hand} | set(board)
    deck = [card for card in range(52) if card not in used]
    shares = [0.0] * len(hands)
    n_boards = 0
    for extra in combinations(deck, 5 - len(board)):
        full = board + list(extra)
        ranks = [evaluate(hand + full) for hand in hands]
        best = max(ranks)
        winners = [i for i, rank in enumerate(ranks) if rank == best]
        for i in winners:
            shares[i] += 1 / len(winners)
        n_boards += 1
    return [share / n_boards for share in shares]


def test_combo_equity_on_a_flop_matches_naive_reference() -> None:
    hands = [cards("As Ks"), cards("Qh Qd"), cards("7c 8c")]
    flop = cards("2c 9c Td")
    expected = naive_equity(hands, flop)
    np.testing.assert_allclose(exact_combo_equity(hands, flop), expected, rtol=0, atol=1e-12)


def test_combo_equity_heads_up_on_a_turn_matches_naive_reference() -> None:
    hands = [cards("Ah Ad"), cards("Kc Qc")]
    turn = cards("Jc Tc 2h 3s")
    expected = naive_equity(hands, turn)
    np.testing.assert_allclose(exact_combo_equity(hands, turn), expected, rtol=0, atol=1e-12)


def test_combo_equity_with_a_complete_board() -> None:
    # Royal flush on the board: everybody splits.
    hands = [cards("2c 3d"), cards("4h 5s")]
    board = cards("Ah Kh Qh Jh Th")
    assert exact_combo_equity(hands, board).tolist() == [0.5, 0.5]


def test_combo_equity_rejects_shared_cards() -> None:
    with pytest.raises(ValueError):
        exact_combo_equity([cards("As Ks"), cards("As Qd")])
    with pytest.raises(ValueError):
        exact_combo_equity([cards("As Ks"), cards("Qh Qd")], cards("As 2c 3d"))


def test_combo_equity_rejects_bad_sizes() -> None:
    with pytest.raises(ValueError):
        exact_combo_equity([cards("As Ks")])
    with pytest.raises(ValueError):
        exact_combo_equity([cards("As Ks"), cards("Qh")])
    with pytest.raises(ValueError):
        exact_combo_equity([cards("As Ks"), cards("Qh Qd")], cards("2c 3d 4h 5s 6c 7d"))


# --- Heads-up equity between classes ----------------------------------------------


def test_aa_vs_kk_matches_published_value() -> None:
    # About 81.9 % / 18.1 % (PokerStrategy forum: 81.946 %).
    aa, kk = heads_up_equity(*classes("AA", "KK"))
    assert aa == pytest.approx(0.819, abs=0.001)
    assert aa + kk == pytest.approx(1.0, abs=1e-12)


def test_ako_vs_22_matches_published_value() -> None:
    # DeucesCracked exact table: AKo wins 46.67 %, ties 0.58 % -> 46.96 % equity.
    ako, deuces = heads_up_equity(*classes("AKo", "22"))
    assert ako == pytest.approx(0.4696, abs=0.001)
    assert ako + deuces == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("name", ["AKs", "22", "T9o"])
def test_same_class_is_exactly_even(name: str) -> None:
    first, second = heads_up_equity(*classes(name, name))
    assert first == pytest.approx(0.5, abs=1e-12)
    assert second == pytest.approx(0.5, abs=1e-12)


def test_heads_up_swapping_players_swaps_equities() -> None:
    a, b = heads_up_equity(*classes("QJs", "A5o"))
    b2, a2 = heads_up_equity(*classes("A5o", "QJs"))
    assert a == pytest.approx(a2, abs=1e-12)
    assert b == pytest.approx(b2, abs=1e-12)


# --- Three-way equity between classes ------------------------------------------------


def test_three_way_shares_sum_to_one() -> None:
    result = three_way_equity(*classes("AKo", "22", "T9s"))
    assert sum(result.three_way) == pytest.approx(1.0, abs=1e-12)
    assert len(result.heads_up) == len(PAIRS) == 3
    assert all(0.0 < value < 1.0 for value in (*result.three_way, *result.heads_up))


def test_three_way_permuting_players_permutes_results() -> None:
    first = three_way_equity(*classes("AKo", "22", "T9s"))
    # Players reordered as (T9s, AKo, 22).
    second = three_way_equity(*classes("T9s", "AKo", "22"))
    np.testing.assert_allclose(
        second.three_way, [first.three_way[2], first.three_way[0], first.three_way[1]], atol=1e-12
    )
    # Pairs (0,1)=T9s-AKo, (0,2)=T9s-22, (1,2)=AKo-22.
    np.testing.assert_allclose(
        second.heads_up,
        [1 - first.heads_up[1], 1 - first.heads_up[2], first.heads_up[0]],
        atol=1e-12,
    )


def test_three_way_matches_monte_carlo() -> None:
    """Independent check with the NumPy evaluator, including E2 with the third hand dead."""
    triplet = classes("AA", "KQs", "76s")
    result = three_way_equity(*triplet)

    representatives, weights = suit_configurations(triplet)
    rng = np.random.default_rng(20261126)
    n = 300_000
    hands = representatives[rng.choice(len(weights), size=n, p=weights / weights.sum())]
    keys = rng.random((n, 52))
    np.put_along_axis(keys, hands, 2.0, axis=1)
    boards = np.argpartition(keys, 5, axis=1)[:, :5]
    values = np.stack(
        [evaluate_batch(np.hstack([hands[:, 2 * p : 2 * p + 2], boards])) for p in range(3)],
        axis=1,
    )
    winners = values == values.max(axis=1, keepdims=True)
    mc_three = (winners / winners.sum(axis=1, keepdims=True)).mean(axis=0)
    mc_pairs = [
        ((values[:, i] > values[:, j]) + 0.5 * (values[:, i] == values[:, j])).mean()
        for i, j in PAIRS
    ]

    tolerance = 5 * 0.5 / np.sqrt(n)  # five standard errors
    np.testing.assert_allclose(result.three_way, mc_three, atol=tolerance)
    np.testing.assert_allclose(result.heads_up, mc_pairs, atol=tolerance)


def test_three_way_rejects_infeasible_triplet() -> None:
    with pytest.raises(ValueError):
        three_way_equity(*classes("AA", "AA", "AA"))


def test_rejects_invalid_class() -> None:
    with pytest.raises(ValueError):
        three_way_equity(0, 1, 169)
    with pytest.raises(ValueError):
        heads_up_equity(-1, 3)
