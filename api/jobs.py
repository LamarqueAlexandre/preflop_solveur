"""Persisted on-demand jobs (principle VII): state lives in SQLite, never in API memory.

Life cycle: ``pending`` -> ``running`` -> ``done`` | ``failed``. The worker
process writes its own transitions, so a finished result survives a crash of
the API. At startup, jobs left ``pending`` or ``running`` by a previous run are
marked ``failed`` (D-019).
"""

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final

INTERRUPTED: Final = "interrompu par un redémarrage de l'API : relancez le calcul"
"""Error of the jobs a restart of the API found unfinished."""


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


UNFINISHED: Final = (JobStatus.PENDING, JobStatus.RUNNING)


@dataclass(frozen=True)
class Job:
    """One on-demand computation, its parameters and, once finished, its outcome."""

    id: str
    kind: str
    status: JobStatus
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str


class JobStore(ABC):
    """Persistent job state. Implementations must be picklable: workers receive them."""

    @abstractmethod
    def create(self, kind: str, params: dict[str, Any]) -> Job:
        """New ``pending`` job."""

    @abstractmethod
    def get(self, job_id: str) -> Job | None:
        """The job, or None if unknown."""

    @abstractmethod
    def start(self, job_id: str) -> bool:
        """``pending`` -> ``running``; False if the job is not pending any more."""

    @abstractmethod
    def finish(self, job_id: str, result: dict[str, Any]) -> None:
        """``running`` -> ``done`` with its JSON-serializable result."""

    @abstractmethod
    def fail(self, job_id: str, error: str) -> bool:
        """Unfinished -> ``failed``; False if the job had already finished."""

    @abstractmethod
    def interrupt_unfinished(self) -> int:
        """Mark every unfinished job ``failed`` (API startup); number of jobs marked."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_COLUMNS: Final = "id, kind, status, params, result, error, created_at, updated_at"
_UNFINISHED_SQL: Final = "status IN ('pending', 'running')"
_BUSY_TIMEOUT_SECONDS: Final = 30.0


class SqliteJobStore(JobStore):
    """Jobs in one SQLite file, shared by the API process and its workers."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(_SCHEMA)

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=_BUSY_TIMEOUT_SECONDS)

    def _update(self, sql: str, *args: object) -> int:
        with closing(self._connect()) as connection, connection:
            return connection.execute(sql, args).rowcount

    def create(self, kind: str, params: dict[str, Any]) -> Job:
        now = _now()
        job = Job(uuid.uuid4().hex, kind, JobStatus.PENDING, params, None, None, now, now)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT INTO jobs ({_COLUMNS}) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                (job.id, kind, job.status.value, json.dumps(params), now, now),
            )
        return job

    def get(self, job_id: str) -> Job | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        id_, kind, status, params, result, error, created_at, updated_at = row
        return Job(
            id=id_,
            kind=kind,
            status=JobStatus(status),
            params=json.loads(params),
            result=json.loads(result) if result is not None else None,
            error=error,
            created_at=created_at,
            updated_at=updated_at,
        )

    def start(self, job_id: str) -> bool:
        return (
            self._update(
                "UPDATE jobs SET status = 'running', updated_at = ? "
                "WHERE id = ? AND status = 'pending'",
                _now(),
                job_id,
            )
            == 1
        )

    def finish(self, job_id: str, result: dict[str, Any]) -> None:
        updated = self._update(
            "UPDATE jobs SET status = 'done', result = ?, updated_at = ? "
            "WHERE id = ? AND status = 'running'",
            json.dumps(result, allow_nan=False),
            _now(),
            job_id,
        )
        if updated != 1:
            raise ValueError(f"job {job_id} is not running")

    def fail(self, job_id: str, error: str) -> bool:
        return (
            self._update(
                f"UPDATE jobs SET status = 'failed', error = ?, updated_at = ? "
                f"WHERE id = ? AND {_UNFINISHED_SQL}",
                error,
                _now(),
                job_id,
            )
            == 1
        )

    def interrupt_unfinished(self) -> int:
        return self._update(
            f"UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE {_UNFINISHED_SQL}",
            INTERRUPTED,
            _now(),
        )
