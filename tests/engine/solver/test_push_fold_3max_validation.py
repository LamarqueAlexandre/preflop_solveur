"""3-max push/fold validation against an independent fictitious play (SC-002.2, SC-002.3, D-004).

No 3-max push/fold Nash chart being published, the DCFR solution of the
push/fold tree is compared with a fictitious play written separately
(``engine.reference``, sharing nothing with ``engine.solver`` but the equity
tensors). The DCFR solution must also be an equilibrium certificate:
NashConv below 0.5% of the starting pot.

Gap measure, at every decision node: combo-weighted mean absolute difference
of the push (or call) frequencies, ``sum_h n_h |f_dcfr(h) - f_fp(h)| / 1326``.

Needs the full equity tensors (``engine equity build``, ~5h, not in CI): the
module is skipped when they are missing.
"""

from pathlib import Path
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from engine.cards import CLASS_WEIGHTS
from engine.equity.storage import DEFAULT_DIRECTORY, StoredEquity, load_tensors, read_manifest
from engine.game import GameConfig, build_push_fold_tree
from engine.realization import default_profile
from engine.reference import DECISION_NODES, PushFoldFictitiousPlay
from engine.solver import DCFRSolver, EquityTables, TerminalValues, exploitability

TENSORS: Final = Path(__file__).parents[3] / DEFAULT_DIRECTORY
STACKS: Final = (5.0, 10.0, 15.0)
MAX_GAP: Final = 0.02
DCFR_ITERATIONS: Final = 500
"""NashConv ~0.0001% of the pot at 10bb after 500 iterations."""
FP_ITERATIONS: Final = 2000
"""At 10bb: fictitious play NashConv ~0.1% of the pot, largest gap ~0.4%."""


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


def frequency_gap(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Combo-weighted mean absolute difference of two per-class frequencies."""
    return float(CLASS_WEIGHTS @ np.abs(a - b)) / float(CLASS_WEIGHTS.sum())


@pytest.fixture(scope="module")
def stored() -> StoredEquity:
    return load_tensors(TENSORS)


@pytest.mark.parametrize("stack", STACKS)
def test_dcfr_matches_the_independent_fictitious_play(stack: float, stored: StoredEquity) -> None:
    tree = build_push_fold_tree(GameConfig.equal_stacks(stack))
    values = TerminalValues(tree, EquityTables.from_stored(stored), default_profile())
    solver = DCFRSolver(tree, values)
    solver.iterate(DCFR_ITERATIONS)
    dcfr = solver.average_strategy()
    certificate = exploitability(tree, values, dcfr)

    reference = PushFoldFictitiousPlay(stored.w, stored.e3, stored.e2, stack)
    reference.iterate(FP_ITERATIONS)
    fp = reference.average_strategy()

    gaps = {node: frequency_gap(dcfr[node][1], fp[node]) for node in DECISION_NODES}
    print(
        f"\n{stack:g}bb: DCFR NashConv {certificate.percent:.4f}% of the pot, "
        f"FP NashConv {reference.nash_conv(fp) / 1.5:.4%}; gaps "
        + ", ".join(f"{node} {gap:.3%}" for node, gap in gaps.items())
    )
    assert certificate.publishable
    assert all(gap < MAX_GAP for gap in gaps.values()), gaps
