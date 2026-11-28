"""Training sessions (US4, D-021), persisted in SQLite.

Storage only: the spots are drawn and graded by the engine (``engine.training``).
The whole session is drawn at creation, so serving a spot or an answer is a
single read (SC-008).
"""

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np

from engine.game import Action, ActionKind, Position
from engine.training import Spot, SpotFilters, SpotType


@dataclass(frozen=True)
class TrainingSession:
    """Drawn spots and the index of the action chosen at each answered one, in order."""

    id: str
    filters: SpotFilters
    seed: int
    spots: tuple[Spot, ...]
    answers: tuple[int, ...]
    created_at: str

    @property
    def finished(self) -> bool:
        return len(self.answers) >= len(self.spots)


class AnswerConflictError(ValueError):
    """The spot was already answered (concurrent or repeated answer), or the session is over."""


class TrainingSessionStore(ABC):
    @abstractmethod
    def create(self, filters: SpotFilters, seed: int, spots: list[Spot]) -> TrainingSession:
        """Save a new session with its drawn spots, none answered."""

    @abstractmethod
    def get(self, session_id: str) -> TrainingSession | None:
        """The session, or None if unknown."""

    @abstractmethod
    def answer(self, session_id: str, index: int, action: int) -> TrainingSession | None:
        """Record ``action`` for spot ``index``, which must be the next unanswered one.

        None if the session is unknown; ``AnswerConflictError`` otherwise.
        """


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _action(action: Action) -> list[Any]:
    return [action.kind.value, action.amount]


def _from_action(value: list[Any]) -> Action:
    return Action(ActionKind(value[0]), float(value[1]))


def _spot(spot: Spot) -> dict[str, Any]:
    return {
        "fingerprint": spot.fingerprint,
        "stack": spot.stack,
        "node_id": spot.node_id,
        "hero": spot.hero.name,
        "spot_type": spot.spot_type.value,
        "history": [[player.name, _action(action)] for player, action in spot.history],
        "hand_class": spot.hand_class,
        "cards": None if spot.cards is None else list(spot.cards),
        "actions": [_action(action) for action in spot.actions],
        "strategy": spot.strategy.tolist(),
        "action_ev": spot.action_ev.tolist(),
    }


def _from_spot(value: dict[str, Any]) -> Spot:
    cards = value["cards"]
    return Spot(
        fingerprint=value["fingerprint"],
        stack=float(value["stack"]),
        node_id=value["node_id"],
        hero=Position[value["hero"]],
        spot_type=SpotType(value["spot_type"]),
        history=tuple(
            (Position[player], _from_action(action)) for player, action in value["history"]
        ),
        hand_class=int(value["hand_class"]),
        cards=None if cards is None else (int(cards[0]), int(cards[1])),
        actions=tuple(_from_action(action) for action in value["actions"]),
        strategy=np.asarray(value["strategy"], dtype=np.float64),
        action_ev=np.asarray(value["action_ev"], dtype=np.float64),
    )


def _filters(filters: SpotFilters) -> dict[str, Any]:
    return {
        "positions": sorted(position.name for position in filters.positions),
        "types": sorted(spot_type.value for spot_type in filters.types),
        "min_stack": filters.min_stack,
        "max_stack": filters.max_stack,
    }


def _from_filters(value: dict[str, Any]) -> SpotFilters:
    return SpotFilters(
        positions=frozenset(Position[name] for name in value["positions"]),
        types=frozenset(SpotType(name) for name in value["types"]),
        min_stack=value["min_stack"],
        max_stack=value["max_stack"],
    )


_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS training_sessions (
    id TEXT PRIMARY KEY,
    filters TEXT NOT NULL,
    seed INTEGER NOT NULL,
    spots TEXT NOT NULL,
    answers TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""
_COLUMNS: Final = "id, filters, seed, spots, answers, created_at"


def _row(row: tuple[Any, ...]) -> TrainingSession:
    id_, filters, seed, spots, answers, created = row
    return TrainingSession(
        id=id_,
        filters=_from_filters(json.loads(filters)),
        seed=int(seed),
        spots=tuple(_from_spot(spot) for spot in json.loads(spots)),
        answers=tuple(int(a) for a in json.loads(answers)),
        created_at=created,
    )


class SqliteTrainingSessionStore(TrainingSessionStore):
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def create(self, filters: SpotFilters, seed: int, spots: list[Spot]) -> TrainingSession:
        session = TrainingSession(uuid.uuid4().hex, filters, seed, tuple(spots), (), _now())
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT INTO training_sessions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    json.dumps(_filters(filters)),
                    seed,
                    json.dumps([_spot(spot) for spot in spots]),
                    "[]",
                    session.created_at,
                ),
            )
        return session

    def get(self, session_id: str) -> TrainingSession | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM training_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _row(row) if row is not None else None

    def answer(self, session_id: str, index: int, action: int) -> TrainingSession | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT answers, json_array_length(spots) FROM training_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            answers: list[int] = json.loads(row[0])
            if index != len(answers) or index >= int(row[1]):
                raise AnswerConflictError(f"spot {index} is not the next unanswered spot")
            # The WHERE clause makes a concurrent answer to the same spot fail.
            updated = connection.execute(
                "UPDATE training_sessions SET answers = ? WHERE id = ? AND answers = ?",
                (json.dumps([*answers, action]), session_id, row[0]),
            ).rowcount
            if updated != 1:
                raise AnswerConflictError(f"spot {index} was answered concurrently")
        return self.get(session_id)
