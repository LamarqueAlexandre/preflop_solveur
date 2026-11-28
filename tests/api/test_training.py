"""Tests of the training session routes (issue #34, US4, FR-025, SC-008, D-021)."""

import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.training import AnswerConflictError, SqliteTrainingSessionStore
from engine.game import GameConfig, Position, build_tree
from engine.library import FileSolutionStore, Solution, SolveParams, solve
from engine.realization import default_profile
from engine.solver import EquityTables, Exploitability
from engine.training import Grade, SpotFilters, draw_spots, grade, summarize

SC_008_SECONDS = 0.3


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
    btn, sb, bb = solution.exploitability.ev
    bad = Exploitability(
        ev=(btn, sb, bb),
        best_response_values=(btn + 1.0, sb + 1.0, bb + 1.0),
        starting_pot=solution.exploitability.starting_pot,
    )
    return replace(solution, exploitability=bad)


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("store")
    store = FileSolutionStore(root)
    for stack in (5.0, 10.0, 15.0):
        store.save(solved(stack))
    store.save(unpublishable(solved(12.0)))
    return root


def make_app(library: Path, sessions: Path) -> Any:
    return create_app(
        FileSolutionStore(library), training_sessions=SqliteTrainingSessionStore(sessions)
    )


@pytest.fixture
def sessions_path(tmp_path: Path) -> Path:
    return tmp_path / "training.sqlite3"


@pytest.fixture
def client(library: Path, sessions_path: Path) -> Iterator[TestClient]:
    with TestClient(make_app(library, sessions_path)) as test_client:
        yield test_client


def published(library: Path) -> dict[str, Solution]:
    store = FileSolutionStore(library)
    return {
        s.fingerprint: store.load(s.fingerprint)
        for s in store.list_solutions(publishable_only=True)
    }


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/training/sessions", json=body)
    assert response.status_code == 201, response.text
    session: dict[str, Any] = response.json()
    return session


def timed(call: Any, *args: Any, **kwargs: Any) -> Any:
    start = time.perf_counter()
    response = call(*args, **kwargs)
    elapsed = time.perf_counter() - start
    assert elapsed < SC_008_SECONDS, f"{elapsed:.3f}s between two spots (SC-008)"
    return response


# --- a full session ----------------------------------------------------------------------


def test_a_full_session_of_20_spots(client: TestClient, library: Path) -> None:
    """US4 independent test: 20 SB spots between 10 and 15bb, answered, then summarized."""
    session = create(client, positions=["SB"], min_stack=10, max_stack=15, seed=7)
    assert session["count"] == 20
    assert session["answered"] == 0 and not session["finished"]
    assert session["positions"] == ["SB"] and session["seed"] == 7
    sid = session["id"]

    chosen: list[int] = []
    for index in range(20):
        spot = timed(client.get, f"/training/sessions/{sid}/spot").json()
        assert spot["index"] == index
        assert spot["hero"] == "SB"  # US4 scenario 1
        assert 10 <= spot["stack"] <= 15
        labels = [action["label"] for action in spot["actions"]]
        choice = index % len(labels)
        chosen.append(choice)
        response = timed(
            client.post, f"/training/sessions/{sid}/answers", json={"action": labels[choice]}
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["spot"] == spot
        assert result["answered"] == index + 1
        assert result["finished"] == (index == 19)

    assert client.get(f"/training/sessions/{sid}").json()["finished"]
    assert client.get(f"/training/sessions/{sid}/spot").status_code == 409
    late = client.post(f"/training/sessions/{sid}/answers", json={"action": "F"})
    assert late.status_code == 409

    # The engine, given the same library, filters and seed, draws and grades the same session.
    filters = SpotFilters(positions=frozenset({Position.SB}), min_stack=10, max_stack=15)
    spots = draw_spots(published(library), filters, 20, 7)
    expected = summarize([grade(spot, c) for spot, c in zip(spots, chosen, strict=True)])
    summary = client.get(f"/training/sessions/{sid}/summary").json()
    assert summary["count"] == summary["answered"] == 20
    assert summary["best"] == expected.best
    assert summary["inaccuracies"] == expected.inaccuracies
    assert summary["mistakes"] == expected.mistakes
    assert summary["score"] == pytest.approx(expected.score)
    assert summary["total_loss"] == pytest.approx(expected.total_loss)
    assert summary["mean_loss"] == pytest.approx(expected.mean_loss)
    errors = [(e.spot.node_id, e.spot.hand, e.grade.value) for e in expected.errors]
    assert [(e["spot"]["node_id"], e["spot"]["hand"], e["grade"]) for e in summary["errors"]] == (
        errors
    )
    # Each error can be opened in the strategy view (US4 scenario 4).
    for error in summary["errors"]:
        node = client.get(
            f"/solutions/{error['spot']['fingerprint']}/nodes/{error['spot']['node_id']}"
        )
        assert node.status_code == 200


# --- spot and answer ---------------------------------------------------------------------


def test_the_spot_hides_the_answer_key(client: TestClient) -> None:
    sid = create(client, seed=1)["id"]
    spot = client.get(f"/training/sessions/{sid}/spot").json()
    assert set(spot) == {
        "index",
        "fingerprint",
        "stack",
        "node_id",
        "hero",
        "spot_type",
        "history",
        "hand",
        "cards",
        "actions",
    }
    assert spot["cards"] is None  # the toy library does not use the 169 classes


def test_the_history_leads_to_the_spot(client: TestClient) -> None:
    sid = create(client, positions=["BB"], seed=3)["id"]
    spot = client.get(f"/training/sessions/{sid}/spot").json()
    assert spot["history"]  # the big blind never acts first
    assert spot["node_id"] == "-".join(step["label"] for step in spot["history"])
    assert [step["actor"] for step in spot["history"]][:1] == ["BTN"]


def test_the_feedback_gives_the_equilibrium_and_the_ev_loss(client: TestClient) -> None:
    """US4 scenario 2: strategy for the hand, EV loss in bb and grade."""
    sid = create(client, seed=11)["id"]
    spot = client.get(f"/training/sessions/{sid}/spot").json()
    choice = spot["actions"][-1]["label"]
    result = client.post(f"/training/sessions/{sid}/answers", json={"action": choice}).json()
    evs = result["action_ev"]
    labels = [action["label"] for action in spot["actions"]]
    assert result["action"] == choice
    assert result["best_action"] == labels[int(np.argmax(evs))]
    assert result["ev_loss"] == pytest.approx(max(evs) - evs[labels.index(choice)])
    assert sum(result["strategy"]) == pytest.approx(1.0)
    assert result["frequency"] == pytest.approx(result["strategy"][labels.index(choice)])
    assert result["grade"] in {"best", "inaccuracy", "mistake"}


def test_a_mixed_action_is_correct(client: TestClient) -> None:
    """US4 scenario 3: an action played at equilibrium is graded best."""
    sid = create(client, seed=5)["id"]
    spot = client.get(f"/training/sessions/{sid}/spot").json()
    first = client.post(
        f"/training/sessions/{sid}/answers", json={"action": spot["actions"][0]["label"]}
    ).json()
    played = [a for a, f in zip(spot["actions"], first["strategy"], strict=True) if f >= 0.01]
    assert played
    # Replay the same spot (same seed) with an action played at equilibrium.
    sid = create(client, seed=5)["id"]
    result = client.post(
        f"/training/sessions/{sid}/answers", json={"action": played[0]["label"]}
    ).json()
    assert result["grade"] == Grade.BEST.value


def test_an_unknown_action_is_rejected(client: TestClient) -> None:
    sid = create(client, seed=2)["id"]
    response = client.post(f"/training/sessions/{sid}/answers", json={"action": "R99"})
    assert response.status_code == 422
    assert client.get(f"/training/sessions/{sid}").json()["answered"] == 0


def test_summary_of_a_session_in_progress(client: TestClient) -> None:
    sid = create(client, count=5, seed=4)["id"]
    empty = client.get(f"/training/sessions/{sid}/summary").json()
    assert empty["count"] == 5 and empty["answered"] == 0
    assert empty["score"] == 0.0 and empty["errors"] == []
    spot = client.get(f"/training/sessions/{sid}/spot").json()
    client.post(f"/training/sessions/{sid}/answers", json={"action": spot["actions"][0]["label"]})
    assert client.get(f"/training/sessions/{sid}/summary").json()["answered"] == 1


# --- creation ----------------------------------------------------------------------------


def test_filters_on_spot_types(client: TestClient) -> None:
    sid = create(client, types=["open"], count=15, seed=9)["id"]
    for _ in range(15):
        spot = client.get(f"/training/sessions/{sid}/spot").json()
        assert spot["spot_type"] == "open"
        assert spot["history"] == [] or all(s["label"] == "F" for s in spot["history"])
        client.post(
            f"/training/sessions/{sid}/answers", json={"action": spot["actions"][0]["label"]}
        )


def test_same_seed_same_spots(client: TestClient) -> None:
    def spots(sid: str) -> list[tuple[str, str]]:
        drawn = []
        for _ in range(5):
            spot = client.get(f"/training/sessions/{sid}/spot").json()
            drawn.append((spot["node_id"], spot["hand"]))
            first_action = spot["actions"][0]["label"]
            client.post(f"/training/sessions/{sid}/answers", json={"action": first_action})
        return drawn

    first = create(client, count=5)
    assert first["seed"] >= 0  # drawn, then returned so the session can be replayed
    replay = create(client, count=5, seed=first["seed"])
    assert spots(first["id"]) == spots(replay["id"])


@pytest.mark.parametrize(
    "body",
    [
        {"min_stack": 30},  # no depth
        {"min_stack": 12, "max_stack": 12},  # only an unpublishable solution
        {"min_stack": 15, "max_stack": 10},
        {"min_stack": 0},
        {"count": 0},
        {"count": 101},
        {"positions": ["UTG"]},
        {"types": ["vs_5bet"]},
        {"seed": -1},
    ],
)
def test_invalid_or_impossible_filters_are_rejected(
    client: TestClient, body: dict[str, Any]
) -> None:
    assert client.post("/training/sessions", json=body).status_code == 422


def test_unknown_session(client: TestClient) -> None:
    sid = "0" * 32
    assert client.get(f"/training/sessions/{sid}").status_code == 404
    assert client.get(f"/training/sessions/{sid}/spot").status_code == 404
    assert client.get(f"/training/sessions/{sid}/summary").status_code == 404
    answer = client.post(f"/training/sessions/{sid}/answers", json={"action": "F"})
    assert answer.status_code == 404
    assert client.get("/training/sessions/not-an-id").status_code == 422


def test_a_session_survives_a_restart(library: Path, sessions_path: Path) -> None:
    with TestClient(make_app(library, sessions_path)) as client:
        sid = create(client, count=3, seed=6)["id"]
        spot = client.get(f"/training/sessions/{sid}/spot").json()
        label = spot["actions"][0]["label"]
        client.post(f"/training/sessions/{sid}/answers", json={"action": label})
    with TestClient(make_app(library, sessions_path)) as client:
        session = client.get(f"/training/sessions/{sid}").json()
        assert session["answered"] == 1
        assert client.get(f"/training/sessions/{sid}/spot").json()["index"] == 1
        summary = client.get(f"/training/sessions/{sid}/summary").json()
        assert summary["answered"] == 1


def test_routes_answer_503_without_a_session_store(library: Path) -> None:
    with TestClient(create_app(FileSolutionStore(library))) as client:
        assert client.post("/training/sessions", json={}).status_code == 503


# --- store -------------------------------------------------------------------------------


def test_the_store_records_answers_in_order(library: Path, tmp_path: Path) -> None:
    store = SqliteTrainingSessionStore(tmp_path / "sessions.sqlite3")
    filters = SpotFilters()
    spots = draw_spots(published(library), filters, 2, 0)
    session = store.create(filters, 0, spots)
    with pytest.raises(AnswerConflictError):
        store.answer(session.id, 1, 0)  # not the next spot
    answered = store.answer(session.id, 0, 1)
    assert answered is not None and answered.answers == (1,)
    with pytest.raises(AnswerConflictError):
        store.answer(session.id, 0, 0)  # already answered
    assert store.answer("0" * 32, 0, 0) is None
    reread = store.get(session.id)
    assert reread is not None
    assert reread.spots[0].history == spots[0].history
    assert reread.spots[0].actions == spots[0].actions
    np.testing.assert_array_equal(reread.spots[0].action_ev, spots[0].action_ev)
    assert reread.filters == filters
