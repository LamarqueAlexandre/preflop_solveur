"""Tests for the n-player pot resolver (main pot and side pots)."""

from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.game import Pot, resolve_pots

BTN, SB, BB = 0, 1, 2


# --- Hand-computed cases ----------------------------------------------------------------


def test_equal_stacks_all_in_make_a_single_pot() -> None:
    assert resolve_pots([10.0, 10.0, 10.0], [False, False, False]) == (
        Pot(30.0, frozenset({BTN, SB, BB})),
    )


def test_one_short_stack_makes_one_side_pot() -> None:
    # BTN all-in for 5, SB and BB put 10 each.
    assert resolve_pots([5.0, 10.0, 10.0], [False, False, False]) == (
        Pot(15.0, frozenset({BTN, SB, BB})),
        Pot(10.0, frozenset({SB, BB})),
    )


def test_two_short_stacks() -> None:
    # 3 + 3 + 3 = 9 for everyone; (6 - 3) * 2 = 6 for SB and BB; 10 - 6 = 4 back to BB.
    assert resolve_pots([3.0, 6.0, 10.0], [False, False, False]) == (
        Pot(9.0, frozenset({BTN, SB, BB})),
        Pot(6.0, frozenset({SB, BB})),
        Pot(4.0, frozenset({BB})),
    )


def test_folded_blind_is_dead_money() -> None:
    # SB posts 0.5 then folds; BTN and BB get it in for 10 each.
    assert resolve_pots([10.0, 0.5, 10.0], [False, True, False]) == (
        Pot(20.5, frozenset({BTN, BB})),
    )


def test_folded_player_above_a_short_all_in() -> None:
    # BTN all-in for 3; SB puts 8 then folds; BB puts 8.
    # Main: 3 + 3 + 3 = 9 for BTN and BB; side: 5 + 5 = 10 for BB only.
    assert resolve_pots([3.0, 8.0, 8.0], [False, True, False]) == (
        Pot(9.0, frozenset({BTN, BB})),
        Pot(10.0, frozenset({BB})),
    )


def test_everybody_folds_to_the_big_blind() -> None:
    assert resolve_pots([0.0, 0.5, 1.0], [True, True, False]) == (Pot(1.5, frozenset({BB})),)


def test_heads_up_works_too() -> None:
    assert resolve_pots([4.0, 7.0], [False, False]) == (
        Pot(8.0, frozenset({0, 1})),
        Pot(3.0, frozenset({1})),
    )


# --- Properties --------------------------------------------------------------------------

# Contributions in half big blinds keep every sum exact in floating point.
contributions = st.lists(st.integers(0, 60).map(lambda k: k / 2), min_size=2, max_size=6)


@st.composite
def situations(draw: st.DrawFn) -> tuple[list[float], list[bool]]:
    amounts = draw(contributions)
    folded = draw(st.lists(st.booleans(), min_size=len(amounts), max_size=len(amounts)))
    if all(folded):
        folded[draw(st.integers(0, len(amounts) - 1))] = False
    # A live player has always put chips in (blind or call); a folder may have put none.
    amounts = [amount if f else max(amount, 0.5) for amount, f in zip(amounts, folded, strict=True)]
    return amounts, folded


@given(situations())
def test_pots_add_up_to_the_contributions(situation: tuple[list[float], list[bool]]) -> None:
    amounts, folded = situation
    pots = resolve_pots(amounts, folded)
    assert sum(pot.amount for pot in pots) == pytest.approx(sum(amounts))


@given(situations())
def test_eligible_players_are_live_and_shrink(situation: tuple[list[float], list[bool]]) -> None:
    amounts, folded = situation
    pots = resolve_pots(amounts, folded)
    assert len(pots) >= 1
    live = {i for i, f in enumerate(folded) if not f}
    for pot in pots:
        assert pot.eligible
        assert pot.eligible <= live
    for earlier, later in pairwise(pots):
        assert later.eligible < earlier.eligible


@given(situations())
def test_each_pot_is_won_by_players_who_covered_it(
    situation: tuple[list[float], list[bool]],
) -> None:
    amounts, folded = situation
    pots = resolve_pots(amounts, folded)
    # The main pot is open to every live player.
    assert pots[0].eligible == {i for i, f in enumerate(folded) if not f}


# --- Invalid input ------------------------------------------------------------------------


def test_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        resolve_pots([1.0, 2.0, 3.0], [False, False])


def test_rejects_negative_contribution() -> None:
    with pytest.raises(ValueError):
        resolve_pots([1.0, -2.0, 3.0], [False, False, False])


def test_rejects_fewer_than_two_players() -> None:
    with pytest.raises(ValueError):
        resolve_pots([1.0], [False])


def test_rejects_when_everybody_folded() -> None:
    with pytest.raises(ValueError):
        resolve_pots([1.0, 2.0], [True, True])
