"""Tests of the on-demand jobs (issue #31): job store, best-response job, restart."""

import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.jobs import INTERRUPTED, JobStatus, SqliteJobStore
from api.worker import ArrayEquity
from engine.best_response import LIMITATIONS, exploit_solution
from engine.cards import format_class
from engine.game import ROOT_ID, GameConfig, build_tree
from engine.game.tree import ActionKind, Position
from engine.library import FileSolutionStore, Solution, SolveParams, solve
from engine.realization import default_profile
from engine.solver import EquityTables, Exploitability, TerminalValues

JOB_TIMEOUT_SECONDS = 120.0


def strength_arrays(strengths: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    s = np.asarray(strengths, dtype=np.float64)
    n = len(s)
    a, b, c = s[:, None, None], s[None, :, None], s[None, None, :]
    e3 = np.broadcast_to(a / (a + b + c), (n, n, n)).copy()
    e2 = np.broadcast_to(a / (a + b), (n, n, n)).copy()
    return np.ones((n, n, n)), e3, e2


ARRAYS = strength_arrays([3.0, 1.0, 2.0, 0.7])
TABLES = EquityTables.from_arrays(*ARRAYS)
OTHER_ARRAYS = strength_arrays([1.0, 2.0, 3.0, 4.0])


def solved(stack: float) -> Solution:
    tree = build_tree(GameConfig.equal_stacks(stack))
    return solve(tree, TABLES, default_profile(), SolveParams(max_iterations=400))


def unpublishable(solution: Solution) -> Solution:
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
    fingerprints = {"15": store.save(solved(15.0))}
    fingerprints["bad"] = store.save(unpublishable(solved(12.0)))
    return root, fingerprints


@pytest.fixture(scope="module")
def fp(library: tuple[Path, dict[str, str]]) -> dict[str, str]:
    return library[1]


@pytest.fixture(scope="module")
def client(
    library: tuple[Path, dict[str, str]], tmp_path_factory: pytest.TempPathFactory
) -> Iterator[TestClient]:
    """One app (and one worker pool) for the module: spawning a pool costs seconds."""
    jobs = SqliteJobStore(tmp_path_factory.mktemp("jobs") / "jobs.sqlite3")
    app = create_app(FileSolutionStore(library[0]), jobs, ArrayEquity(*ARRAYS))
    with TestClient(app) as test_client:
        yield test_client


def root_lock(solution: Solution, kind: ActionKind) -> list[list[float]]:
    """The BTN always plays ``kind`` at the root, whatever the hand."""
    actions = solution.tree.node(ROOT_ID).actions
    lock = np.zeros((len(actions), len(solution.hand_mass)))
    lock[[a.kind for a in actions].index(kind)] = 1.0
    return lock.tolist()


def wait_job(client: TestClient, job_id: str) -> dict[str, Any]:
    """Job once finished (done or failed)."""
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(f"/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} not finished after {JOB_TIMEOUT_SECONDS}s")


def start(client: TestClient, fingerprint: str, hero: str, locks: dict[str, Any]) -> Any:
    return client.post(
        "/best-response", json={"fingerprint": fingerprint, "hero": hero, "locks": locks}
    )


# --- Job store ---------------------------------------------------------------------------


def test_job_life_cycle(tmp_path: Path) -> None:
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite3")
    job = jobs.create("best_response", {"x": 1})
    assert job.status is JobStatus.PENDING
    assert jobs.get(job.id) == job
    assert jobs.start(job.id)
    assert not jobs.start(job.id), "a running job cannot start again"
    assert jobs.get(job.id).status is JobStatus.RUNNING  # type: ignore[union-attr]
    jobs.finish(job.id, {"gain": 0.25})
    done = jobs.get(job.id)
    assert done is not None
    assert done.status is JobStatus.DONE
    assert done.result == {"gain": 0.25}
    assert done.params == {"x": 1}
    assert not jobs.fail(job.id, "too late"), "a finished job keeps its outcome"


def test_failed_job_keeps_its_error(tmp_path: Path) -> None:
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite3")
    job = jobs.create("best_response", {})
    assert jobs.fail(job.id, "boom")
    failed = jobs.get(job.id)
    assert failed is not None
    assert failed.status is JobStatus.FAILED
    assert failed.error == "boom"
    assert failed.result is None
    with pytest.raises(ValueError):
        jobs.finish(job.id, {})


def test_unknown_job_in_store(tmp_path: Path) -> None:
    assert SqliteJobStore(tmp_path / "jobs.sqlite3").get("0" * 32) is None


def test_interrupt_unfinished(tmp_path: Path) -> None:
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite3")
    pending, running, done = (jobs.create("best_response", {}) for _ in range(3))
    jobs.start(running.id)
    jobs.start(done.id)
    jobs.finish(done.id, {})
    assert jobs.interrupt_unfinished() == 2
    for job_id in (pending.id, running.id):
        job = jobs.get(job_id)
        assert job is not None
        assert job.status is JobStatus.FAILED
        assert job.error == INTERRUPTED
    assert jobs.get(done.id).status is JobStatus.DONE  # type: ignore[union-attr]


# --- POST /best-response and GET /jobs/{id} ----------------------------------------------


def test_best_response_job(
    client: TestClient, library: tuple[Path, dict[str, str]], fp: dict[str, str]
) -> None:
    """Job created, finished, and its result is the engine's (SC-007 setting: BTN shoves)."""
    solution = FileSolutionStore(library[0]).load(fp["15"])
    locks = {ROOT_ID: root_lock(solution, ActionKind.ALL_IN)}
    response = start(client, fp["15"], "SB", locks)
    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "pending"
    assert created["kind"] == "best_response"
    assert created["result"] is None

    body = wait_job(client, created["id"])
    assert body["status"] == "done", body["error"]
    assert body["error"] is None
    result = body["result"]

    expected = exploit_solution(
        solution,
        TerminalValues(solution.tree, TABLES, solution.profile),
        {ROOT_ID: np.asarray(locks[ROOT_ID])},
        Position.SB,
    )
    assert result["fingerprint"] == fp["15"]
    assert result["hero"] == "SB"
    assert result["locked_nodes"] == [ROOT_ID]
    assert result["value"] == pytest.approx(expected.value)
    assert result["equilibrium_ev"] == pytest.approx(expected.equilibrium_ev)
    assert result["gain"] == pytest.approx(expected.gain)
    assert result["gain"] >= 0.0
    assert result["limitations"] == list(LIMITATIONS)
    assert [h["hand"] for h in result["hands"]] == [format_class(h) for h in range(4)]
    assert [h["gain"] for h in result["hands"]] == pytest.approx(expected.hand_gain.tolist())

    assert [n["node_id"] for n in result["nodes"]] == list(expected.nodes)
    for node in result["nodes"]:
        engine_node = expected.nodes[node["node_id"]]
        assert len(node["actions"]) == len(engine_node.actions)
        for h, hand in enumerate(node["hands"]):
            assert hand["equilibrium"] == pytest.approx(engine_node.equilibrium[:, h].tolist())
            assert hand["best"] == pytest.approx(engine_node.best[:, h].tolist())
            assert hand["frequency_gap"] == pytest.approx(engine_node.frequency_gap[:, h].tolist())
            gain = engine_node.ev_gain[h]
            assert hand["ev_gain"] == (None if np.isnan(gain) else pytest.approx(gain))


def test_failed_job(
    library: tuple[Path, dict[str, str]], fp: dict[str, str], tmp_path: Path
) -> None:
    """Tensors other than the solution's: the job fails with an explicit error."""
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite3")
    app = create_app(FileSolutionStore(library[0]), jobs, ArrayEquity(*OTHER_ARRAYS))
    solution = FileSolutionStore(library[0]).load(fp["15"])
    with TestClient(app) as client:
        created = start(client, fp["15"], "SB", {ROOT_ID: root_lock(solution, ActionKind.FOLD)})
        body = wait_job(client, created.json()["id"])
    assert body["status"] == "failed"
    assert body["result"] is None
    assert "equity tensors" in body["error"]


def test_job_survives_a_restart(
    library: tuple[Path, dict[str, str]], fp: dict[str, str], tmp_path: Path
) -> None:
    """A finished job is read back by a new API on the same job database."""
    path = tmp_path / "jobs.sqlite3"
    solution = FileSolutionStore(library[0]).load(fp["15"])
    locks = {ROOT_ID: root_lock(solution, ActionKind.ALL_IN)}
    with TestClient(
        create_app(FileSolutionStore(library[0]), SqliteJobStore(path), ArrayEquity(*ARRAYS))
    ) as first:
        job_id = start(first, fp["15"], "SB", locks).json()["id"]
        before = wait_job(first, job_id)
    assert before["status"] == "done"
    with TestClient(
        create_app(FileSolutionStore(library[0]), SqliteJobStore(path), ArrayEquity(*ARRAYS))
    ) as second:
        after = second.get(f"/jobs/{job_id}").json()
    assert after == before


def test_restart_fails_unfinished_jobs(
    library: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite3")
    left_over = jobs.create("best_response", {})
    with TestClient(create_app(FileSolutionStore(library[0]), jobs, ArrayEquity(*ARRAYS))) as c:
        body = c.get(f"/jobs/{left_over.id}").json()
    assert body["status"] == "failed"
    assert body["error"] == INTERRUPTED


# --- Invalid requests --------------------------------------------------------------------


def test_lock_on_the_hero_is_rejected(
    client: TestClient, library: tuple[Path, dict[str, str]], fp: dict[str, str]
) -> None:
    solution = FileSolutionStore(library[0]).load(fp["15"])
    response = start(client, fp["15"], "BTN", {ROOT_ID: root_lock(solution, ActionKind.FOLD)})
    assert response.status_code == 422
    assert "hero" in response.json()["detail"]


@pytest.mark.parametrize(
    "lock",
    [
        [[1.0, 0.0, 0.0, 0.0]],  # one row instead of one per action
        [[0.5] * 4, [0.0] * 4, [0.0] * 4],  # rows do not sum to 1
        [[1.0, 0.0], [0.0, 1.0]],  # wrong number of classes
        [[1.0], [0.0, 1.0]],  # ragged
        [[-1.0] * 4, [2.0] * 4],  # negative frequency
    ],
)
def test_invalid_lock_is_rejected(client: TestClient, fp: dict[str, str], lock: Any) -> None:
    assert start(client, fp["15"], "SB", {ROOT_ID: lock}).status_code == 422


def test_unknown_node_and_empty_locks_are_rejected(client: TestClient, fp: dict[str, str]) -> None:
    assert start(client, fp["15"], "SB", {"R99": [[1.0] * 4]}).status_code == 422
    assert start(client, fp["15"], "SB", {}).status_code == 422


def test_invalid_hero_is_rejected(client: TestClient, fp: dict[str, str]) -> None:
    assert start(client, fp["15"], "UTG", {ROOT_ID: [[1.0] * 4]}).status_code == 422


def test_unknown_or_unpublishable_solution(client: TestClient, fp: dict[str, str]) -> None:
    lock = {ROOT_ID: [[1.0] * 4]}
    assert start(client, "0" * 64, "SB", lock).status_code == 404
    assert start(client, fp["bad"], "SB", lock).status_code == 404
    assert start(client, "../etc", "SB", lock).status_code == 422


def test_unknown_job_route(client: TestClient) -> None:
    assert client.get(f"/jobs/{'0' * 32}").status_code == 404
    assert client.get("/jobs/not-a-job").status_code == 422


def test_jobs_off_without_configuration(library: tuple[Path, dict[str, str]]) -> None:
    with TestClient(create_app(FileSolutionStore(library[0]))) as client:
        assert client.get(f"/jobs/{'0' * 32}").status_code == 503


def test_openapi_schema_describes_the_job_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert {"/best-response", "/jobs/{job_id}"} <= schema["paths"].keys()
    assert {"BestResponseIn", "BestResponseOut", "JobOut"} <= schema["components"]["schemas"].keys()
