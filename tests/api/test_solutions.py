"""Tests of the solution routes (issue #30): list, nearest depth, node reading."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.game import ROOT_ID, GameConfig, build_tree
from engine.library import FileSolutionStore, Solution, SolveParams, solve
from engine.realization import default_profile
from engine.solver import EquityTables, Exploitability


def strength_tables(strengths: list[float]) -> EquityTables:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return EquityTables.from_arrays(np.ones((n, n, n)), e3, e2)


TABLES = strength_tables([3.0, 1.0, 2.0, 0.7])


def solved(stack: float) -> Solution:
    tree = build_tree(GameConfig.equal_stacks(stack))
    return solve(tree, TABLES, default_profile(), SolveParams(max_iterations=400))


def unpublishable(solution: Solution) -> Solution:
    """Same solution with an exploitability far above the 0.5% threshold."""
    btn, sb, bb = solution.exploitability.ev
    bad = Exploitability(
        ev=(btn, sb, bb),
        best_response_values=(btn + 1.0, sb + 1.0, bb + 1.0),
        starting_pot=solution.exploitability.starting_pot,
    )
    return replace(solution, exploitability=bad)


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("store")
    store = FileSolutionStore(root)
    fingerprints = {"10": store.save(solved(10.0)), "15": store.save(solved(15.0))}
    fingerprints["bad"] = store.save(unpublishable(solved(12.0)))
    return root, fingerprints


@pytest.fixture
def client(library: tuple[Path, dict[str, str]]) -> Iterator[TestClient]:
    with TestClient(create_app(FileSolutionStore(library[0]))) as test_client:
        yield test_client


@pytest.fixture
def fp(library: tuple[Path, dict[str, str]]) -> dict[str, str]:
    return library[1]


def test_published_solutions_are_publishable(library: tuple[Path, dict[str, str]]) -> None:
    store = FileSolutionStore(library[0])
    assert store.summary(library[1]["10"]).publishable
    assert not store.summary(library[1]["bad"]).publishable


# --- GET /solutions ----------------------------------------------------------------------


def test_list_gives_publishable_solutions_by_depth(client: TestClient, fp: dict[str, str]) -> None:
    response = client.get("/solutions")
    assert response.status_code == 200
    body = response.json()
    assert [s["fingerprint"] for s in body] == [fp["10"], fp["15"]]
    assert body[0]["depth"] == 10.0
    assert body[0]["stacks"] == [10.0, 10.0, 10.0]
    assert body[0]["profile_name"] == default_profile().name
    assert body[0]["nash_conv_percent"] < 0.5


def test_empty_library_gives_an_empty_list(tmp_path: Path) -> None:
    with TestClient(create_app(FileSolutionStore(tmp_path))) as client:
        assert client.get("/solutions").json() == []


# --- GET /solutions/nearest --------------------------------------------------------------


def test_nearest_exact(client: TestClient, fp: dict[str, str]) -> None:
    body = client.get("/solutions/nearest", params={"stack": 15}).json()
    assert body["exact"] is True
    assert body["requested_stack"] == 15.0
    assert body["solution"]["fingerprint"] == fp["15"]


def test_nearest_missing_depth(client: TestClient, fp: dict[str, str]) -> None:
    """12bb exists but is not publishable: 10bb is the closest published depth."""
    body = client.get("/solutions/nearest", params={"stack": 12}).json()
    assert body["exact"] is False
    assert body["solution"]["fingerprint"] == fp["10"]


@pytest.mark.parametrize("stack", ["0", "-5", "abc"])
def test_nearest_invalid_stack(client: TestClient, stack: str) -> None:
    assert client.get("/solutions/nearest", params={"stack": stack}).status_code == 422


def test_nearest_in_an_empty_library(tmp_path: Path) -> None:
    with TestClient(create_app(FileSolutionStore(tmp_path))) as client:
        assert client.get("/solutions/nearest", params={"stack": 15}).status_code == 404


# --- GET /solutions/{fingerprint}/nodes/{node_id} ----------------------------------------


def test_root_node(client: TestClient, fp: dict[str, str]) -> None:
    response = client.get(f"/solutions/{fp['15']}/nodes/{ROOT_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "decision"
    assert body["actor"] == "BTN"
    assert body["profile_name"] == default_profile().name
    n_actions = len(body["actions"])
    assert n_actions >= 2
    assert {"kind", "amount", "label", "child_id"} <= body["actions"][0].keys()
    summary = body["summary"]
    assert summary["reached"] is True
    assert sum(summary["frequencies"]) == pytest.approx(1.0)
    assert summary["pot"] == pytest.approx(1.5)
    assert len(body["hands"]) == 4  # the toy tables have four hand classes
    hand = body["hands"][0]
    assert hand["hand"] == "AA"
    assert hand["combos"] == 6
    assert len(hand["strategy"]) == len(hand["action_ev"]) == n_actions
    assert sum(hand["strategy"]) == pytest.approx(1.0)
    assert len(hand["ev"]) == len(hand["reach"]) == 3


def test_the_api_follows_the_engine(client: TestClient, fp: dict[str, str]) -> None:
    """The route only reshapes the engine arrays: no computation of its own."""
    solution = solved(15.0)
    node = solution.node(ROOT_ID)
    body = client.get(f"/solutions/{fp['15']}/nodes/{ROOT_ID}").json()
    for h, hand in enumerate(body["hands"]):
        assert hand["strategy"] == pytest.approx(node.strategy[:, h].tolist())
        assert hand["action_ev"] == pytest.approx(node.action_ev[:, h].tolist())


def test_navigation_to_a_child(client: TestClient, fp: dict[str, str]) -> None:
    root = client.get(f"/solutions/{fp['15']}/nodes/{ROOT_ID}").json()
    child_id = next(a["child_id"] for a in root["actions"] if a["kind"] == "R")
    child = client.get(f"/solutions/{fp['15']}/nodes/{child_id}").json()
    assert child["type"] == "decision"
    assert child["actor"] == "SB"
    assert child["node_id"] == child_id


def test_terminal_node(client: TestClient, fp: dict[str, str]) -> None:
    """Everybody folds to the BB, who wins the blinds: +0.5bb, SB -0.5bb."""
    body = client.get(f"/solutions/{fp['15']}/nodes/F-F").json()
    assert body["type"] == "terminal"
    assert body["kind"] == "fold"
    assert body["pot"] == pytest.approx(1.5)
    assert body["folded"] == [True, True, False]
    assert body["ev"] == pytest.approx([0.0, -0.5, 0.5])


def test_unknown_node(client: TestClient, fp: dict[str, str]) -> None:
    assert client.get(f"/solutions/{fp['15']}/nodes/R99").status_code == 404


def test_unknown_solution(client: TestClient) -> None:
    response = client.get(f"/solutions/{'0' * 64}/nodes/{ROOT_ID}")
    assert response.status_code == 404


def test_unpublishable_solution_is_not_served(client: TestClient, fp: dict[str, str]) -> None:
    assert client.get(f"/solutions/{fp['bad']}/nodes/{ROOT_ID}").status_code == 404


@pytest.mark.parametrize("fingerprint", ["..", "abc", "Z" * 64, "%2e%2e%2fdata"])
def test_malformed_fingerprint_is_rejected(client: TestClient, fingerprint: str) -> None:
    assert client.get(f"/solutions/{fingerprint}/nodes/{ROOT_ID}").status_code in (404, 422)


# --- OpenAPI schema ----------------------------------------------------------------------


def test_openapi_schema_describes_the_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert {"/solutions", "/solutions/nearest", "/solutions/{fingerprint}/nodes/{node_id}"} <= (
        paths.keys()
    )
    models = schema["components"]["schemas"]
    assert {"SolutionOut", "DecisionNodeOut", "TerminalNodeOut", "HandOut"} <= models.keys()
