"""Tests for ``solve`` and the ``Solution`` object (FR-009, FR-011, D-015)."""

from collections.abc import Iterator
from dataclasses import replace
from importlib.metadata import version

import numpy as np
import pytest

from engine.game import ROOT_ID, GameConfig, Position, build_tree
from engine.library import NodeSolution, Solution, SolveParams, solve
from engine.realization import default_profile
from engine.solver import DCFRParams, EquityTables, Exploitability

STRONG, WEAK = 0, 1


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


TABLES = strength_tables([3.0, 1.0, 2.0, 0.7])


@pytest.fixture(scope="module")
def solution() -> Solution:
    tree = build_tree(GameConfig.equal_stacks(12.0))
    return solve(tree, TABLES, default_profile(), SolveParams(max_iterations=400))


# --- Parameters (D-015) ------------------------------------------------------------------


def test_default_parameters_follow_d015() -> None:
    params = SolveParams()
    assert params.max_iterations == 2000
    assert params.target_percent == 0.1
    assert params.check_every == 100
    assert params.dcfr == DCFRParams()


@pytest.mark.parametrize(
    "changes",
    [
        {"max_iterations": 0},
        {"check_every": 0},
        {"target_percent": 0.0},
        {"target_percent": -1.0},
    ],
)
def test_invalid_parameters_are_rejected(changes: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        replace(SolveParams(), **changes)


# --- Stopping rule -----------------------------------------------------------------------


def test_solve_stops_at_the_first_check_below_the_target() -> None:
    tree = build_tree(GameConfig.equal_stacks(5.0))
    checks: list[tuple[int, Exploitability]] = []
    params = SolveParams(max_iterations=1000, target_percent=0.5, check_every=10)
    result = solve(
        tree, TABLES, default_profile(), params, progress=lambda i, e: checks.append((i, e))
    )
    assert result.iterations % 10 == 0
    assert result.iterations == checks[-1][0]
    assert checks[-1][1].percent < 0.5
    assert all(e.percent >= 0.5 for _, e in checks[:-1])
    assert [i for i, _ in checks] == list(range(10, result.iterations + 1, 10))
    assert result.exploitability == checks[-1][1]


def test_solve_stops_at_the_iteration_cap_when_the_target_is_out_of_reach() -> None:
    tree = build_tree(GameConfig.equal_stacks(20.0))
    params = SolveParams(max_iterations=25, target_percent=1e-12, check_every=10)
    checks: list[int] = []
    result = solve(tree, TABLES, default_profile(), params, progress=lambda i, _: checks.append(i))
    assert checks == [10, 20, 25]
    assert result.iterations == 25
    assert result.exploitability.percent >= 1e-12


def test_publishable_follows_the_half_percent_threshold() -> None:
    tree = build_tree(GameConfig.equal_stacks(20.0))
    rough = solve(tree, TABLES, default_profile(), SolveParams(max_iterations=1, check_every=1))
    assert rough.exploitability.percent >= 0.5
    assert not rough.publishable


def test_the_profile_must_be_the_one_named_by_the_config() -> None:
    tree = build_tree(GameConfig.equal_stacks(5.0, realization_profile="other"))
    with pytest.raises(ValueError, match="profile"):
        solve(tree, TABLES, default_profile())


# --- Content of a solution ---------------------------------------------------------------


def test_solution_records_how_it_was_computed(solution: Solution) -> None:
    profile = default_profile()
    assert solution.config == GameConfig.equal_stacks(12.0)
    assert solution.profile_name == profile.name
    assert solution.profile_version == profile.version
    assert solution.params == SolveParams(max_iterations=400)
    assert 0 < solution.iterations <= 400
    assert solution.duration_seconds > 0
    assert solution.publishable
    assert solution.exploitability.percent < 0.1


def test_solution_strategy_is_the_average_strategy(solution: Solution) -> None:
    decisions = [node.id for node in solution.tree if not node.is_terminal]
    assert sorted(solution.strategy) == sorted(decisions)
    for node_id, played in solution.strategy.items():
        node = solution.tree.node(node_id)
        assert played.shape == (len(node.actions), TABLES.n_classes)
        np.testing.assert_allclose(played.sum(axis=0), 1.0)


def nodes(solution: Solution) -> Iterator[NodeSolution]:
    for node in solution.tree:
        if not node.is_terminal:
            yield solution.node(node.id)


def test_node_view_gives_strategy_action_evs_and_reaches(solution: Solution) -> None:
    root = solution.node(ROOT_ID)
    assert root.node_id == ROOT_ID
    assert root.actor is Position.BTN
    assert root.actions == solution.tree.root.actions
    np.testing.assert_array_equal(root.strategy, solution.strategy[ROOT_ID])
    np.testing.assert_allclose(root.reach, np.ones((3, TABLES.n_classes)))
    for child_index, child in enumerate(solution.tree.root.children):
        np.testing.assert_array_equal(
            root.action_ev[child_index], solution.values.ev_at(child)[int(Position.BTN)]
        )


def test_node_ev_is_the_strategy_weighted_ev_of_the_actions(solution: Solution) -> None:
    for view in nodes(solution):
        actor = int(view.actor)
        reached = ~np.isnan(view.ev[actor])
        expected = (view.strategy * view.action_ev).sum(axis=0)
        np.testing.assert_allclose(view.ev[actor][reached], expected[reached], atol=1e-9)


def test_root_evs_are_the_exploitability_evs(solution: Solution) -> None:
    assert solution.root_ev() == pytest.approx(solution.exploitability.ev)
    assert sum(solution.root_ev()) == pytest.approx(0.0, abs=1e-9)


def test_terminal_nodes_have_no_node_view(solution: Solution) -> None:
    terminal = next(node.id for node in solution.tree if node.is_terminal)
    with pytest.raises(ValueError, match="terminal"):
        solution.node(terminal)
    with pytest.raises(KeyError):
        solution.node("nope")


# --- Provenance (D-016) ------------------------------------------------------------------


def test_solution_records_its_provenance(solution: Solution) -> None:
    assert solution.engine_version == version("preflop-solveur")
    assert solution.equity_digest == TABLES.digest
    assert solution.profile == default_profile()
