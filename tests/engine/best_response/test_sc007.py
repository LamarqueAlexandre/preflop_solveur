"""SC-007 reference test (US3): the BTN opens 100% at 15bb, best response of the SB.

At 15bb (9-15bb tranche, D-011) the only open raise below all-in is R2.0; the
SB facing it can fold, call or go all-in. Against a BTN opening every hand,
the SB best response must gain EV (D-006) and go all-in with a wider range
than at equilibrium, keeping every hand it already shoves.

Needs the full equity tensors (``engine equity build``): skipped otherwise.
The 15bb solution is read from ``data/solutions`` when stored with the
current fingerprint, else solved (about 30 s). See docs/notes/sc007.md.
"""

from pathlib import Path
from typing import Final

import numpy as np
import pytest

from engine.best_response import ExploitResult, exploit_solution
from engine.cards import CLASS_WEIGHTS
from engine.equity.storage import DEFAULT_DIRECTORY, load_tensors, read_manifest
from engine.game import ROOT_ID, ActionKind, GameConfig, Position, build_tree
from engine.library import (
    FileSolutionStore,
    Solution,
    SolveParams,
    engine_version,
    fingerprint,
    solve,
)
from engine.realization import default_profile
from engine.solver import EquityTables, TerminalValues

ROOT: Final = Path(__file__).parents[3]
TENSORS: Final = ROOT / DEFAULT_DIRECTORY
STORE: Final = ROOT / "data" / "solutions"
STACK: Final = 15.0
OPEN: Final = "R2.0"


def _tensors_available() -> bool:
    try:
        return read_manifest(TENSORS).classes is None
    except (FileNotFoundError, ValueError):
        return False


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not _tensors_available(), reason="full equity tensors missing (engine equity build)"
    ),
]


def combo_frequency(strategy_row: np.ndarray) -> float:
    """Share of the 1326 combos playing an action."""
    return float(CLASS_WEIGHTS @ strategy_row) / float(CLASS_WEIGHTS.sum())


@pytest.fixture(scope="module")
def tables() -> EquityTables:
    return EquityTables.from_stored(load_tensors(TENSORS))


@pytest.fixture(scope="module")
def solution(tables: EquityTables) -> Solution:
    tree = build_tree(GameConfig.equal_stacks(STACK))
    profile, params = default_profile(), SolveParams()
    key = fingerprint(tree, profile, params, tables.digest, engine_version())
    if STORE.is_dir() and FileSolutionStore(STORE).contains(key):
        return FileSolutionStore(STORE).load(key)
    return solve(tree, tables, profile, params)


@pytest.fixture(scope="module")
def result(solution: Solution, tables: EquityTables) -> ExploitResult:
    root = solution.tree.root
    tokens = [action.token for action in root.actions]
    lock = np.zeros((len(root.actions), solution.hand_mass.shape[0]))
    lock[tokens.index(OPEN)] = 1.0
    values = TerminalValues(solution.tree, tables, solution.profile)
    return exploit_solution(solution, values, {ROOT_ID: lock}, Position.SB)


def all_in_row(result: ExploitResult) -> int:
    node = result.nodes[OPEN]
    return [action.kind for action in node.actions].index(ActionKind.ALL_IN)


def test_the_scenario_is_the_one_of_sc007(solution: Solution) -> None:
    assert solution.publishable
    assert OPEN in [action.token for action in solution.tree.root.actions]
    assert solution.tree.node(OPEN).actor is Position.SB


def test_the_sb_best_response_gains_ev(result: ExploitResult) -> None:
    assert result.gain > 0
    assert result.value > result.equilibrium_ev


def test_the_sb_all_in_range_is_wider_than_at_equilibrium(result: ExploitResult) -> None:
    node = result.nodes[OPEN]
    row = all_in_row(result)
    assert combo_frequency(node.best[row]) > combo_frequency(node.equilibrium[row])


def test_every_equilibrium_shove_is_still_a_shove(result: ExploitResult) -> None:
    node = result.nodes[OPEN]
    row = all_in_row(result)
    shoved = node.equilibrium[row] > 1e-3
    assert (node.best[row][shoved] >= node.equilibrium[row][shoved] - 1e-9).all()
