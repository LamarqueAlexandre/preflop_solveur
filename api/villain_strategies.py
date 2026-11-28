"""Saved villain strategies (FR-017, D-020), persisted in SQLite.

Storage only: the strategies are validated by the engine before they get here.
"""

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class VillainStrategyData:
    """What the user gives: a named strategy of one node, actions by label."""

    name: str
    description: str
    actor: str
    actions: list[str]
    frequencies: list[list[float]]
    fingerprint: str | None = None
    node_id: str | None = None


@dataclass(frozen=True)
class VillainStrategy:
    id: str
    data: VillainStrategyData
    created_at: str
    updated_at: str


class DuplicateNameError(ValueError):
    """Another saved strategy already has this name (case-insensitive)."""


class VillainStrategyStore(ABC):
    @abstractmethod
    def create(self, data: VillainStrategyData) -> VillainStrategy:
        """Save a new strategy; ``DuplicateNameError`` if the name is taken."""

    @abstractmethod
    def list(self) -> list[VillainStrategy]:
        """Every saved strategy, by name."""

    @abstractmethod
    def get(self, strategy_id: str) -> VillainStrategy | None:
        """The strategy, or None if unknown."""

    @abstractmethod
    def update(self, strategy_id: str, data: VillainStrategyData) -> VillainStrategy | None:
        """Replace a strategy; None if unknown, ``DuplicateNameError`` if the name is taken."""

    @abstractmethod
    def delete(self, strategy_id: str) -> bool:
        """Delete a strategy; False if unknown."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS villain_strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL,
    actor TEXT NOT NULL,
    actions TEXT NOT NULL,
    frequencies TEXT NOT NULL,
    fingerprint TEXT,
    node_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_COLUMNS: Final = (
    "id, name, description, actor, actions, frequencies, fingerprint, node_id, "
    "created_at, updated_at"
)


def _row(row: tuple[str, ...]) -> VillainStrategy:
    id_, name, description, actor, actions, frequencies, fingerprint, node_id, created, updated = (
        row
    )
    data = VillainStrategyData(
        name=name,
        description=description,
        actor=actor,
        actions=json.loads(actions),
        frequencies=json.loads(frequencies),
        fingerprint=fingerprint,
        node_id=node_id,
    )
    return VillainStrategy(id_, data, created, updated)


def _values(data: VillainStrategyData) -> tuple[object, ...]:
    return (
        data.name,
        data.description,
        data.actor,
        json.dumps(data.actions),
        json.dumps(data.frequencies, allow_nan=False),
        data.fingerprint,
        data.node_id,
    )


class SqliteVillainStrategyStore(VillainStrategyStore):
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def create(self, data: VillainStrategyData) -> VillainStrategy:
        now = _now()
        strategy = VillainStrategy(uuid.uuid4().hex, data, now, now)
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    f"INSERT INTO villain_strategies ({_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (strategy.id, *_values(data), now, now),
                )
        except sqlite3.IntegrityError:
            raise DuplicateNameError(f"a strategy named {data.name!r} already exists") from None
        return strategy

    def list(self) -> list[VillainStrategy]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM villain_strategies ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [_row(row) for row in rows]

    def get(self, strategy_id: str) -> VillainStrategy | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM villain_strategies WHERE id = ?", (strategy_id,)
            ).fetchone()
        return _row(row) if row is not None else None

    def update(self, strategy_id: str, data: VillainStrategyData) -> VillainStrategy | None:
        try:
            with closing(self._connect()) as connection, connection:
                updated = connection.execute(
                    "UPDATE villain_strategies SET name = ?, description = ?, actor = ?, "
                    "actions = ?, frequencies = ?, fingerprint = ?, node_id = ?, updated_at = ? "
                    "WHERE id = ?",
                    (*_values(data), _now(), strategy_id),
                ).rowcount
        except sqlite3.IntegrityError:
            raise DuplicateNameError(f"a strategy named {data.name!r} already exists") from None
        return self.get(strategy_id) if updated == 1 else None

    def delete(self, strategy_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            deleted = connection.execute(
                "DELETE FROM villain_strategies WHERE id = ?", (strategy_id,)
            ).rowcount
        return bool(deleted == 1)
