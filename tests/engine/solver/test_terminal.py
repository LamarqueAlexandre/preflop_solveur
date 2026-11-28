"""Tests for terminal values: fold, all-in showdown, flop with realization (#18).

Hand-made equity tables use a "strength" model: class a has strength s[a],
its three-way share against b and c is s[a] / (s[a] + s[b] + s[c]) and its
heads-up share against b is s[a] / (s[a] + s[b]). Classes 0 ("strong", s=3)
and 1 ("weak", s=1) give round numbers: 0.6 / 0.2 / 0.2 three-way, 0.75 / 0.25
heads-up.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from engine.equity.storage import DEFAULT_DIRECTORY, load_tensors
from engine.game import GameConfig, Position, TerminalKind, build_tree
from engine.realization import (
    FORMAT_VERSION,
    FlopPosition,
    RealizationProfile,
    all_keys,
    default_profile,
    parse_profile,
)
from engine.solver import EquityTables, TerminalValues

STRONG, WEAK = 0, 1
ONE_HOT = {STRONG: np.array([1.0, 0.0]), WEAK: np.array([0.0, 1.0])}

# --- Helpers ---------------------------------------------------------------------------


def strength_arrays(
    strengths: Sequence[float], w: NDArray[np.float64] | None = None
) -> tuple[NDArray[Any], NDArray[Any], NDArray[Any]]:
    """W (ones by default), E3 and E2 of the strength model."""
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    weights = np.ones((n, n, n)) if w is None else w
    return weights, e3, e2


def strength_tables(
    strengths: Sequence[float], w: NDArray[np.float64] | None = None
) -> EquityTables:
    return EquityTables.from_arrays(*strength_arrays(strengths, w))


def profile_with(
    factors: dict[tuple[int, FlopPosition], float], name: str = "test"
) -> RealizationProfile:
    """A profile where (players, position) gets the given factor in every context, else 1."""
    entries = [
        {
            "players": key.players,
            "pot_type": key.pot_type.value,
            "tranche": key.tranche.value,
            "position": key.position.value,
            "factor": factors.get((key.players, key.position), 1.0),
        }
        for key in all_keys()
    ]
    return parse_profile(
        {
            "format_version": FORMAT_VERSION,
            "name": name,
            "version": "1.0.0",
            "description": "test profile",
            "entries": entries,
        }
    )


FLAT = profile_with({}, "flat")


def evaluator(
    stacks: tuple[float, float, float],
    tables: EquityTables | None = None,
    profile: RealizationProfile = FLAT,
) -> TerminalValues:
    tree = build_tree(GameConfig(stacks=stacks))
    return TerminalValues(tree, tables or strength_tables([3.0, 1.0]), profile)


def one_hot(btn: int, sb: int, bb: int) -> tuple[NDArray[Any], NDArray[Any], NDArray[Any]]:
    return ONE_HOT[btn], ONE_HOT[sb], ONE_HOT[bb]


def random_symmetric_weights(n: int, rng: np.random.Generator) -> NDArray[np.float64]:
    """Random integer weights invariant under axis permutations, with some zeros."""
    raw = rng.integers(0, 4, size=(n, n, n)).astype(np.float64)
    perms = [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]
    return sum(raw.transpose(p) for p in perms)  # type: ignore[return-value]


TEN = (10.0, 10.0, 10.0)

# --- Fold ------------------------------------------------------------------------------


def test_fold_winner_takes_the_pot() -> None:
    """BTN opens to 2bb, SB and BB fold: +1.5 / -0.5 / -1, whatever the hands."""
    values = evaluator(TEN)
    for hands in [(STRONG, WEAK, WEAK), (WEAK, STRONG, STRONG)]:
        ev = values.expected_values("R2.0-F-F", one_hot(*hands))
        assert ev == pytest.approx((1.5, -0.5, -1.0))


# --- All-in showdown ---------------------------------------------------------------------


def test_three_way_all_in() -> None:
    """Pot 30bb: strong BTN gets 0.6, weak SB and BB 0.2 each."""
    ev = evaluator(TEN).expected_values("A-C-C", one_hot(STRONG, WEAK, WEAK))
    assert ev == pytest.approx((30 * 0.6 - 10, 30 * 0.2 - 10, 30 * 0.2 - 10))


def test_heads_up_all_in_with_dead_money() -> None:
    """SB folds its blind: pot 20.5bb, strong BTN 0.75 against weak BB."""
    ev = evaluator(TEN).expected_values("A-F-C", one_hot(STRONG, WEAK, WEAK))
    assert ev == pytest.approx((20.5 * 0.75 - 10, -0.5, 20.5 * 0.25 - 10))


def test_side_pot() -> None:
    """Stacks 5/10/10: main pot 15bb three-way, side pot 10bb SB vs BB (BTN dead)."""
    ev = evaluator((5.0, 10.0, 10.0)).expected_values("A-A-C", one_hot(WEAK, STRONG, WEAK))
    assert ev == pytest.approx(
        (
            15 * 0.2 - 5,
            15 * 0.6 + 10 * 0.75 - 10,
            15 * 0.2 + 10 * 0.25 - 10,
        )
    )


def test_counterfactual_values_of_each_hand() -> None:
    """v_i(h) = sum over opponents' hands of W * reach * reach * payoff."""
    values = evaluator(TEN)
    reaches = (np.ones(2), ONE_HOT[WEAK], ONE_HOT[WEAK])
    v_btn = values.values("A-C-C", Position.BTN, reaches)
    # strong BTN against two weak hands: 30 * 0.6 - 10; weak against weak: 30 / 3 - 10
    np.testing.assert_allclose(v_btn, [8.0, 0.0])


def test_counterfactual_values_weight_by_reach_and_card_removal() -> None:
    w = np.ones((2, 2, 2))
    w[STRONG, STRONG, :] = w[STRONG, :, STRONG] = w[:, STRONG, STRONG] = 0.0  # one STRONG combo
    values = evaluator(TEN, strength_tables([3.0, 1.0], w))
    reaches = (np.ones(2), np.array([1.0, 0.5]), np.array([1.0, 0.5]))
    v_btn = values.values("A-C-C", Position.BTN, reaches)
    # BTN strong: only weak/weak opponents remain (reach 0.5 * 0.5): 0.25 * 8
    assert v_btn[STRONG] == pytest.approx(0.25 * 8.0)


# --- Flop --------------------------------------------------------------------------------


def test_heads_up_flop_with_realization() -> None:
    """BTN opens 2bb, SB folds, BB calls: pot 4.5bb, BTN in position (R 1.2, BB 0.8)."""
    profile = profile_with({(2, FlopPosition.IP): 1.2, (2, FlopPosition.OOP): 0.8})
    ev = evaluator(TEN, profile=profile).expected_values("R2.0-F-C", one_hot(STRONG, WEAK, WEAK))
    share_btn = 1.2 * 0.75 / (1.2 * 0.75 + 0.8 * 0.25)  # 9 / 11
    assert ev == pytest.approx((4.5 * share_btn - 2, -0.5, 4.5 * (1 - share_btn) - 2))


def test_three_way_flop_with_realization() -> None:
    """Limped pot of 3bb: SB first (0.8), BB middle (1.0), BTN last (1.2)."""
    profile = profile_with(
        {(3, FlopPosition.FIRST): 0.8, (3, FlopPosition.MIDDLE): 1.0, (3, FlopPosition.LAST): 1.2}
    )
    ev = evaluator(TEN, profile=profile).expected_values("C-C-X", one_hot(WEAK, STRONG, WEAK))
    weighted = {"btn": 1.2 * 0.2, "sb": 0.8 * 0.6, "bb": 1.0 * 0.2}
    total = sum(weighted.values())
    assert ev == pytest.approx(tuple(3 * weighted[p] / total - 1 for p in ("btn", "sb", "bb")))


def test_flat_profile_gives_raw_equity_at_the_flop() -> None:
    ev = evaluator(TEN).expected_values("R2.0-F-C", one_hot(STRONG, WEAK, WEAK))
    assert ev == pytest.approx((4.5 * 0.75 - 2, -0.5, 4.5 * 0.25 - 2))


def test_flop_with_a_live_all_in_player_is_not_supported() -> None:
    """Stacks 5/10/10, BTN all-in called twice: a side pot at the flop (V2, D-013)."""
    values = evaluator((5.0, 10.0, 10.0))
    with pytest.raises(NotImplementedError, match="D-013"):
        values.expected_values("A-C-C", one_hot(WEAK, WEAK, WEAK))


# --- No realization on all-in pots -------------------------------------------------------


EXTREME = profile_with(
    {
        (2, FlopPosition.IP): 5.0,
        (2, FlopPosition.OOP): 0.2,
        (3, FlopPosition.FIRST): 0.2,
        (3, FlopPosition.MIDDLE): 1.0,
        (3, FlopPosition.LAST): 5.0,
    },
    "extreme",
)


@pytest.mark.parametrize("stack", [6.0, 12.0, 20.0])
def test_realization_never_applies_to_all_in_or_fold(stack: float) -> None:
    rng = np.random.default_rng(18)
    tables = strength_tables([3.0, 1.0, 2.0, 0.5])
    tree = build_tree(GameConfig.equal_stacks(stack))
    flat = TerminalValues(tree, tables, FLAT)
    extreme = TerminalValues(tree, tables, EXTREME)
    reaches = tuple(rng.random(4) for _ in range(3))
    flop_differs = False
    for node in tree:
        if not node.is_terminal:
            continue
        for player in Position:
            a = flat.values(node.id, player, reaches)
            b = extreme.values(node.id, player, reaches)
            if node.terminal is TerminalKind.FLOP:
                flop_differs |= not np.allclose(a, b)
            else:
                np.testing.assert_array_equal(a, b)
    assert flop_differs


# --- Constant sum ------------------------------------------------------------------------


@pytest.mark.parametrize("stack", [3.0, 8.0, 12.0, 20.0, 25.0])
def test_expected_values_sum_to_zero_at_every_terminal(stack: float) -> None:
    rng = np.random.default_rng(int(stack))
    n = 5
    tables = strength_tables(rng.uniform(0.5, 3.0, n), random_symmetric_weights(n, rng))
    tree = build_tree(GameConfig.equal_stacks(stack))
    values = TerminalValues(tree, tables, default_profile())
    for _ in range(3):
        reaches = tuple(rng.random(n) for _ in range(3))
        for node in tree:
            if node.is_terminal:
                assert sum(values.expected_values(node.id, reaches)) == pytest.approx(
                    0.0, abs=1e-9
                ), node.id


def test_expected_values_match_counterfactual_values() -> None:
    rng = np.random.default_rng(7)
    n = 4
    w = random_symmetric_weights(n, rng)
    tables = strength_tables(rng.uniform(0.5, 3.0, n), w)
    values = TerminalValues(build_tree(GameConfig.equal_stacks(20.0)), tables, default_profile())
    reaches = tuple(rng.random(n) for _ in range(3))
    reach_mass = np.einsum("abc,a,b,c->", w, *reaches)
    for node_id in ["R2.0-F-F", "A-C-C", "A-F-C", "R2.0-F-C", "C-C-X"]:
        ev = values.expected_values(node_id, reaches)
        for player in Position:
            v = values.values(node_id, player, reaches)
            assert ev[player] == pytest.approx(float(reaches[player] @ v) / reach_mass)


# --- Equity tables -----------------------------------------------------------------------


def test_tables_replace_nan_of_impossible_triplets() -> None:
    w, e3, e2 = strength_arrays([3.0, 1.0])
    w[STRONG, STRONG, STRONG] = 0.0
    e3_nan, e2_nan = e3.copy(), e2.copy()
    e3_nan[STRONG, STRONG, STRONG] = np.nan
    e2_nan[STRONG, STRONG, STRONG] = np.nan
    clean = EquityTables.from_arrays(w, e3, e2)
    with_nan = EquityTables.from_arrays(w, e3_nan, e2_nan)
    assert np.isfinite(with_nan.e3).all() and np.isfinite(with_nan.e2).all()
    reaches = tuple(np.ones(2) for _ in range(3))
    for tables in (clean, with_nan):
        assert np.isfinite(
            TerminalValues(build_tree(GameConfig.equal_stacks(10.0)), tables, FLAT).values(
                "A-C-C", Position.BTN, reaches
            )
        ).all()


def test_tables_renormalize_shares_of_each_triplet() -> None:
    w, e3, e2 = strength_arrays([3.0, 1.0, 2.0])
    tables = EquityTables.from_arrays(w, e3 * 1.01, e2 * 0.99)
    np.testing.assert_allclose(tables.e3, e3, rtol=0, atol=1e-15)
    np.testing.assert_allclose(tables.e2, e2, rtol=0, atol=1e-15)
    assert tables.e3.dtype == np.float64


def test_tables_reject_inconsistent_shapes() -> None:
    w, e3, e2 = strength_arrays([3.0, 1.0])
    with pytest.raises(ValueError):
        EquityTables.from_arrays(w, e3[:1], e2)


def test_tables_reject_asymmetric_weights() -> None:
    w, e3, e2 = strength_arrays([3.0, 1.0])
    w[0, 0, 1] = 5.0
    with pytest.raises(ValueError, match="symmetric"):
        EquityTables.from_arrays(w, e3, e2)


def test_reaches_must_match_the_number_of_classes() -> None:
    values = evaluator(TEN)
    with pytest.raises(ValueError):
        values.values("A-C-C", Position.BTN, (np.ones(3), np.ones(3), np.ones(3)))


def test_values_only_at_terminals() -> None:
    with pytest.raises(ValueError):
        evaluator(TEN).values("root", Position.BTN, (np.ones(2), np.ones(2), np.ones(2)))


# --- Real tensors ------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    not (Path(DEFAULT_DIRECTORY) / "manifest.json").is_file(), reason="no equity tensors"
)
def test_real_tensors_sum_to_zero() -> None:
    tables = EquityTables.from_stored(load_tensors(verify=False))
    tree = build_tree(GameConfig.equal_stacks(20.0))
    values = TerminalValues(tree, tables, default_profile())
    rng = np.random.default_rng(2026)
    reaches = tuple(rng.random(169) for _ in range(3))
    for node in tree:
        if node.is_terminal:
            assert sum(values.expected_values(node.id, reaches)) == pytest.approx(0.0, abs=1e-9)


# --- Digest of the tables (D-016) ----------------------------------------------------------


def test_digest_identifies_the_tables() -> None:
    a = strength_tables([3.0, 1.0, 2.0])
    assert len(a.digest) == 64
    assert a.digest == strength_tables([3.0, 1.0, 2.0]).digest
    assert a.digest != strength_tables([3.0, 1.0, 2.5]).digest
    assert a.digest != strength_tables([3.0, 1.0]).digest
