"""Tests of the saved villain strategies routes (issue #32, FR-017, D-020)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.villain_strategies import SqliteVillainStrategyStore
from engine.cards import N_CLASSES, parse_class
from engine.library import FileSolutionStore

ACTIONS = ["F", "C", "R2.0", "A"]


def frequencies(action: int = 2) -> list[list[float]]:
    """Every hand plays ``action``."""
    return [[1.0 if a == action else 0.0] * N_CLASSES for a in range(len(ACTIONS))]


def body(name: str = "BTN ouvre tout", **changes: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": "ouverture à 2x à 100 %",
        "actor": "BTN",
        "actions": ACTIONS,
        "frequencies": frequencies(),
        "fingerprint": "a" * 64,
        "node_id": "root",
    } | changes


def make_app(tmp_path: Path) -> Any:
    return create_app(
        FileSolutionStore(tmp_path / "store"),
        villains=SqliteVillainStrategyStore(tmp_path / "villains.sqlite3"),
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(make_app(tmp_path)) as test_client:
        yield test_client


# --- create / read -----------------------------------------------------------------------


def test_create_then_read(client: TestClient) -> None:
    response = client.post("/villain-strategies", json=body())
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "BTN ouvre tout"
    assert created["actor"] == "BTN"
    assert created["actions"] == ACTIONS
    assert created["frequencies"] == frequencies()
    assert created["fingerprint"] == "a" * 64
    assert created["node_id"] == "root"
    assert len(created["id"]) == 32
    assert created["created_at"] == created["updated_at"]

    read = client.get(f"/villain-strategies/{created['id']}")
    assert read.status_code == 200
    assert read.json() == created


def test_origin_and_description_are_optional(client: TestClient) -> None:
    minimal = {
        k: v for k, v in body().items() if k not in ("description", "fingerprint", "node_id")
    }
    created = client.post("/villain-strategies", json=minimal).json()
    assert created["description"] == ""
    assert created["fingerprint"] is None
    assert created["node_id"] is None


def test_name_is_trimmed(client: TestClient) -> None:
    assert client.post("/villain-strategies", json=body("  BTN large  ")).json()["name"] == (
        "BTN large"
    )


def test_duplicate_name_is_refused_whatever_the_case(client: TestClient) -> None:
    assert client.post("/villain-strategies", json=body("BTN large")).status_code == 201
    response = client.post("/villain-strategies", json=body("btn LARGE"))
    assert response.status_code == 409
    assert "btn LARGE" in response.json()["detail"]


# --- invalid strategies ------------------------------------------------------------------


def test_an_incomplete_strategy_is_refused_with_its_hands(client: TestClient) -> None:
    """Spec edge case: frequencies of a hand that do not total 100%."""
    freqs = frequencies()
    freqs[2][parse_class("AKs")] = 0.6
    freqs[0][parse_class("72o")] = 0.5
    response = client.post("/villain-strategies", json=body(frequencies=freqs))
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert set(detail["hands"]) == {"AKs", "72o"}
    assert "probability" in detail["message"]


@pytest.mark.parametrize(
    "changes",
    [
        {"frequencies": frequencies()[:3]},  # one row missing
        {"frequencies": [row[:13] for row in frequencies()]},  # 13 hands instead of 169
        {"actions": ["F", "F", "R2.0", "A"]},  # repeated label
        {"actions": [], "frequencies": []},
    ],
)
def test_malformed_strategies_are_refused(client: TestClient, changes: dict[str, Any]) -> None:
    response = client.post("/villain-strategies", json=body(**changes))
    assert response.status_code == 422
    assert response.json()["detail"]["hands"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"actor": "UTG"},
        {"fingerprint": "not-a-fingerprint"},
    ],
)
def test_invalid_fields_are_refused(client: TestClient, changes: dict[str, Any]) -> None:
    assert client.post("/villain-strategies", json=body(**changes)).status_code == 422


# --- list --------------------------------------------------------------------------------


def test_list_by_name_without_frequencies(client: TestClient) -> None:
    for name in ("SB serrée", "btn large", "BB défend"):
        client.post("/villain-strategies", json=body(name))
    listed = client.get("/villain-strategies").json()
    assert [s["name"] for s in listed] == ["BB défend", "btn large", "SB serrée"]
    assert all("frequencies" not in s for s in listed)
    assert listed[0]["actions"] == ACTIONS


def test_empty_list(client: TestClient) -> None:
    assert client.get("/villain-strategies").json() == []


# --- replace -----------------------------------------------------------------------------


def test_replace(client: TestClient) -> None:
    created = client.post("/villain-strategies", json=body()).json()
    response = client.put(
        f"/villain-strategies/{created['id']}",
        json=body("BTN fold tout", frequencies=frequencies(0), node_id=None),
    )
    assert response.status_code == 200
    replaced = response.json()
    assert replaced["id"] == created["id"]
    assert replaced["name"] == "BTN fold tout"
    assert replaced["frequencies"] == frequencies(0)
    assert replaced["node_id"] is None
    assert replaced["created_at"] == created["created_at"]
    assert replaced["updated_at"] >= created["updated_at"]
    assert client.get(f"/villain-strategies/{created['id']}").json() == replaced


def test_replace_keeping_its_own_name(client: TestClient) -> None:
    created = client.post("/villain-strategies", json=body()).json()
    response = client.put(f"/villain-strategies/{created['id']}", json=body(description="v2"))
    assert response.status_code == 200


def test_replace_with_a_taken_name(client: TestClient) -> None:
    client.post("/villain-strategies", json=body("A"))
    other = client.post("/villain-strategies", json=body("B")).json()
    assert client.put(f"/villain-strategies/{other['id']}", json=body("a")).status_code == 409


def test_replace_with_an_invalid_strategy(client: TestClient) -> None:
    created = client.post("/villain-strategies", json=body()).json()
    bad = frequencies()
    bad[2][0] = 0.0
    response = client.put(f"/villain-strategies/{created['id']}", json=body(frequencies=bad))
    assert response.status_code == 422
    assert response.json()["detail"]["hands"] == ["AA"]


def test_replace_unknown(client: TestClient) -> None:
    assert client.put(f"/villain-strategies/{'0' * 32}", json=body()).status_code == 404


# --- delete ------------------------------------------------------------------------------


def test_delete(client: TestClient) -> None:
    created = client.post("/villain-strategies", json=body()).json()
    response = client.delete(f"/villain-strategies/{created['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/villain-strategies/{created['id']}").status_code == 404
    assert client.delete(f"/villain-strategies/{created['id']}").status_code == 404
    assert client.post("/villain-strategies", json=body()).status_code == 201, "name freed"


# --- unknown, malformed, not configured, persistence -------------------------------------


def test_unknown_or_malformed_id(client: TestClient) -> None:
    assert client.get(f"/villain-strategies/{'0' * 32}").status_code == 404
    assert client.get("/villain-strategies/xyz").status_code == 422


def test_routes_off_without_configuration(tmp_path: Path) -> None:
    with TestClient(create_app(FileSolutionStore(tmp_path))) as client:
        assert client.get("/villain-strategies").status_code == 503


def test_strategies_survive_a_restart(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as first:
        created = first.post("/villain-strategies", json=body()).json()
    with TestClient(make_app(tmp_path)) as second:
        assert second.get(f"/villain-strategies/{created['id']}").json() == created


def test_openapi_schema_describes_the_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert {"/villain-strategies", "/villain-strategies/{strategy_id}"} <= schema["paths"].keys()
    assert {"get", "put", "delete"} <= schema["paths"]["/villain-strategies/{strategy_id}"].keys()
    assert {"VillainStrategyIn", "VillainStrategyOut", "InvalidStrategyOut"} <= (
        schema["components"]["schemas"].keys()
    )
