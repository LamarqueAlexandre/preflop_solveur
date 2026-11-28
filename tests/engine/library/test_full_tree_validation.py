"""Full preflop tree solved with the real equity tensors (FR-009, FR-011, SC-001).

Acceptance of issue #23: NashConv below 0.5% of the starting pot on one depth
per tranche (<= 8bb, 9-15bb, > 15bb), and node EVs consistent with the EVs of
the actions.

Needs the full equity tensors (``engine equity build``, ~5h, not in CI): the
module is skipped when they are missing. About 3 minutes.
"""

from pathlib import Path
from typing import Final

import numpy as np
import pytest

from engine.equity.storage import DEFAULT_DIRECTORY, load_tensors, read_manifest
from engine.game import ROOT_ID, GameConfig, build_tree
from engine.library import Solution, SolveParams, solve
from engine.realization import default_profile
from engine.solver import PUBLICATION_THRESHOLD_PERCENT, EquityTables

TENSORS: Final = Path(__file__).parents[3] / DEFAULT_DIRECTORY
STACKS: Final = (5.0, 12.0, 20.0)


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


@pytest.fixture(scope="module")
def tables() -> EquityTables:
    return EquityTables.from_stored(load_tensors(TENSORS))


@pytest.fixture(scope="module", params=STACKS, ids=lambda s: f"{s:g}bb")
def solution(request: pytest.FixtureRequest, tables: EquityTables) -> Solution:
    tree = build_tree(GameConfig.equal_stacks(request.param))
    return solve(tree, tables, default_profile(), SolveParams())


def test_solution_is_publishable(solution: Solution) -> None:
    assert solution.exploitability.percent < PUBLICATION_THRESHOLD_PERCENT
    assert solution.publishable


def test_node_evs_are_consistent_with_the_action_evs(solution: Solution) -> None:
    for node in solution.tree:
        if node.is_terminal:
            continue
        view = solution.node(node.id)
        actor = int(view.actor)
        reached = ~np.isnan(view.ev[actor])
        expected = (view.strategy * view.action_ev).sum(axis=0)
        np.testing.assert_allclose(view.ev[actor][reached], expected[reached], atol=1e-9)


def test_root_evs_sum_to_zero(solution: Solution) -> None:
    assert sum(solution.root_ev()) == pytest.approx(0.0, abs=1e-9)
    assert solution.node(ROOT_ID).reach.min() == 1.0
