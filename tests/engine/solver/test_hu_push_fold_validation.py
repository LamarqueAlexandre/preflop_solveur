"""Heads-up push/fold validation against the published Nash charts (SC-002.1, D-004).

The BTN is forced to fold: what is left is the heads-up push/fold game between
SB and BB, whose chipEV Nash equilibrium HoldemResources publishes
(``data/hrc_hu_push_fold_no_ante.csv``). The BTN's dead hand changes nothing:
averaged over it, the SB vs BB equities and combo weights are exactly the
heads-up ones (docs/notes/push-fold-heads-up.md).

Gap measure: combo-weighted mean absolute difference of frequencies,
``sum_h n_h |f_solver(h) - f_chart(h)| / 1326``, for the SB push and the BB call.

Needs the full equity tensors (``engine equity build``, ~5h, not in CI): the
module is skipped when they are missing.
"""

import csv
from pathlib import Path
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from engine.cards import CLASS_WEIGHTS, N_CLASSES, parse_class
from engine.equity.storage import DEFAULT_DIRECTORY, load_tensors, read_manifest
from engine.game import GameConfig, build_heads_up_push_fold_tree
from engine.realization import default_profile
from engine.solver import DCFRSolver, EquityTables, TerminalValues, exploitability

REFERENCE: Final = Path(__file__).parent / "data" / "hrc_hu_push_fold_no_ante.csv"
TENSORS: Final = Path(__file__).parents[3] / DEFAULT_DIRECTORY
STACKS: Final = (5.0, 10.0, 15.0)
MAX_GAP: Final = 0.02
ITERATIONS: Final = 3000


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


def load_reference() -> dict[tuple[float, str], NDArray[np.float64]]:
    """Chart frequencies by (stack, side), one value per hand class."""
    reference = {
        (stack, side): np.zeros(N_CLASSES) for stack in STACKS for side in ("push", "call")
    }
    with REFERENCE.open(encoding="utf-8") as handle:
        rows = csv.DictReader(line for line in handle if not line.startswith("#"))
        for row in rows:
            key = (float(row["stack"]), row["side"])
            reference[key][parse_class(row["hand"])] = float(row["frequency"])
    return reference


def frequency_gap(solver: NDArray[np.float64], chart: NDArray[np.float64]) -> float:
    """Combo-weighted mean absolute difference of two per-class frequencies."""
    return float(CLASS_WEIGHTS @ np.abs(solver - chart)) / float(CLASS_WEIGHTS.sum())


@pytest.fixture(scope="module")
def tables() -> EquityTables:
    return EquityTables.from_stored(load_tensors(TENSORS))


@pytest.fixture(scope="module")
def reference() -> dict[tuple[float, str], NDArray[np.float64]]:
    return load_reference()


def test_reference_matches_the_published_chart_examples(
    reference: dict[tuple[float, str], NDArray[np.float64]],
) -> None:
    """Spot checks of the chart page: T3s pushed at 5bb, Q2o called at 5bb, not at 10bb."""
    assert reference[5.0, "push"][parse_class("T3s")] == 1.0
    assert reference[10.0, "push"][parse_class("T3s")] == 0.0
    assert reference[5.0, "call"][parse_class("Q2o")] == 1.0
    assert reference[10.0, "call"][parse_class("Q2o")] == 0.0
    assert all(reference[stack, "push"][parse_class("AA")] == 1.0 for stack in STACKS)


@pytest.mark.parametrize("stack", STACKS)
def test_heads_up_subcase_matches_the_nash_chart(
    stack: float,
    tables: EquityTables,
    reference: dict[tuple[float, str], NDArray[np.float64]],
) -> None:
    tree = build_heads_up_push_fold_tree(GameConfig.equal_stacks(stack))
    values = TerminalValues(tree, tables, default_profile())
    solver = DCFRSolver(tree, values)
    solver.iterate(ITERATIONS)
    profile = solver.average_strategy()

    push_gap = frequency_gap(profile["F"][1], reference[stack, "push"])
    call_gap = frequency_gap(profile["F-A"][1], reference[stack, "call"])
    certificate = exploitability(tree, values, profile)
    print(
        f"\n{stack:g}bb: SB push gap {push_gap:.3%}, BB call gap {call_gap:.3%}, "
        f"NashConv {certificate.percent:.4f}% of the pot"
    )
    assert push_gap < MAX_GAP
    assert call_gap < MAX_GAP
    assert certificate.publishable
