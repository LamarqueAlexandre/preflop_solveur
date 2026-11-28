"""Solution store: abstract interface and file implementation (FR-012, FR-013, principle VII).

``FileSolutionStore`` keeps one directory per fingerprint::

    <root>/<fingerprint>/manifest.json   metadata, config, tree, profile, parameters
    <root>/<fingerprint>/arrays.npz      strategy, reach, opponent mass, EV, hand mass
    <root>/index.sqlite                  one row per solution, for the lists

The directories are the source of truth; the SQLite index is a cache that
``rebuild_index`` recreates. A solution is written in a temporary directory
then renamed: an interrupted write leaves a ``.tmp-*`` directory, ignored,
never a half-written solution (D-016).
"""

import hashlib
import json
import shutil
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from engine.library.fingerprint import FINGERPRINT_SCHEMA, solution_fingerprint
from engine.library.serialization import (
    config_from_data,
    config_to_data,
    exploitability_from_data,
    exploitability_to_data,
    params_from_data,
    params_to_data,
    profile_from_data,
    profile_to_data,
    tree_from_data,
    tree_to_data,
)
from engine.library.solution import Solution
from engine.solver import NodeValues, Strategy

STORE_FORMAT_VERSION: Final = 1
"""Version of the on-disk layout of a solution."""

MANIFEST: Final = "manifest.json"
ARRAYS: Final = "arrays.npz"
INDEX: Final = "index.sqlite"
_TEMPORARY_PREFIX: Final = ".tmp-"

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS solutions (
    fingerprint TEXT PRIMARY KEY,
    stack_btn REAL NOT NULL,
    stack_sb REAL NOT NULL,
    stack_bb REAL NOT NULL,
    tranche TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    format_version INTEGER NOT NULL,
    nash_conv_percent REAL NOT NULL,
    publishable INTEGER NOT NULL,
    iterations INTEGER NOT NULL,
    created_at TEXT NOT NULL
)
"""
_COLUMNS: Final = (
    "fingerprint, stack_btn, stack_sb, stack_bb, tranche, profile_name, profile_version, "
    "engine_version, format_version, nash_conv_percent, publishable, iterations, created_at"
)


class StoreError(ValueError):
    """An unreadable, corrupted or unsupported stored solution."""


@dataclass(frozen=True)
class SolutionSummary:
    """One line of the solution list."""

    fingerprint: str
    stacks: tuple[float, float, float]
    tranche: str
    profile_name: str
    profile_version: str
    engine_version: str
    format_version: int
    nash_conv_percent: float
    publishable: bool
    iterations: int
    created_at: str


class SolutionStore(ABC):
    """Where solutions are kept, by fingerprint (principle VII)."""

    @abstractmethod
    def save(self, solution: Solution) -> str:
        """Store a solution and return its fingerprint; a stored fingerprint is left as is."""

    @abstractmethod
    def load(self, fingerprint: str) -> Solution:
        """The stored solution; ``KeyError`` if absent."""

    @abstractmethod
    def contains(self, fingerprint: str) -> bool:
        """Whether a solution with this fingerprint is stored."""

    @abstractmethod
    def summary(self, fingerprint: str) -> SolutionSummary:
        """Summary of a stored solution; ``KeyError`` if absent."""

    @abstractmethod
    def list_solutions(self, publishable_only: bool = False) -> list[SolutionSummary]:
        """Summaries sorted by stacks."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _readonly(array: NDArray[np.float64]) -> NDArray[np.float64]:
    array.flags.writeable = False
    return array


def _summary_row(manifest: dict[str, Any]) -> tuple[object, ...]:
    config = config_from_data(manifest["config"])
    profile = manifest["profile"]
    return (
        manifest["fingerprint"],
        *config.stacks,
        config.tranche.value,
        profile["name"],
        profile["version"],
        manifest["engine_version"],
        manifest["format_version"],
        manifest["exploitability"]["percent"],
        int(bool(manifest["publishable"])),
        manifest["iterations"],
        manifest["created_at"],
    )


def _summary(row: tuple[Any, ...]) -> SolutionSummary:
    return SolutionSummary(
        fingerprint=row[0],
        stacks=(row[1], row[2], row[3]),
        tranche=row[4],
        profile_name=row[5],
        profile_version=row[6],
        engine_version=row[7],
        format_version=row[8],
        nash_conv_percent=row[9],
        publishable=bool(row[10]),
        iterations=row[11],
        created_at=row[12],
    )


class FileSolutionStore(SolutionStore):
    """One directory per fingerprint under ``root``, plus a SQLite index."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(_SCHEMA)

    @property
    def root(self) -> Path:
        return self._root

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._root / INDEX)

    def _index(self, manifest: dict[str, Any]) -> None:
        placeholders = ", ".join("?" * len(_COLUMNS.split(",")))
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT OR REPLACE INTO solutions ({_COLUMNS}) VALUES ({placeholders})",
                _summary_row(manifest),
            )

    def _read_manifest(self, fingerprint: str) -> dict[str, Any]:
        path = self._root / fingerprint / MANIFEST
        if not path.is_file():
            raise KeyError(fingerprint)
        try:
            manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StoreError(f"cannot read the manifest of {fingerprint}: {error}") from error
        found = manifest.get("format_version")
        if found != STORE_FORMAT_VERSION:
            raise StoreError(
                f"solution {fingerprint}: unsupported store format version {found!r}, "
                f"expected {STORE_FORMAT_VERSION}"
            )
        return manifest

    def contains(self, fingerprint: str) -> bool:
        return (self._root / fingerprint / MANIFEST).is_file()

    def save(self, solution: Solution) -> str:
        fingerprint = solution_fingerprint(solution)
        if self.contains(fingerprint):
            self._index(self._read_manifest(fingerprint))
            return fingerprint

        temporary = self._root / f"{_TEMPORARY_PREFIX}{uuid.uuid4().hex}"
        temporary.mkdir()
        try:
            decisions = [node.id for node in solution.tree if not node.is_terminal]
            values = solution.values
            np.savez_compressed(
                temporary / ARRAYS,
                strategy=np.concatenate([solution.strategy[node_id] for node_id in decisions]),
                reach=values.reach,
                opponent_mass=values.opponent_mass,
                ev=values.ev,
                hand_mass=solution.hand_mass,
            )
            manifest = {
                "format_version": STORE_FORMAT_VERSION,
                "fingerprint": fingerprint,
                "fingerprint_schema": FINGERPRINT_SCHEMA,
                "engine_version": solution.engine_version,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "n_classes": int(solution.hand_mass.shape[0]),
                "config": config_to_data(solution.config),
                "tree": tree_to_data(solution.tree),
                "profile": profile_to_data(solution.profile),
                "params": params_to_data(solution.params),
                "equity_digest": solution.equity_digest,
                "iterations": solution.iterations,
                "duration_seconds": solution.duration_seconds,
                "exploitability": exploitability_to_data(solution.exploitability),
                "publishable": solution.publishable,
                "checksums": {ARRAYS: _sha256(temporary / ARRAYS)},
            }
            (temporary / MANIFEST).write_text(
                json.dumps(manifest, indent=1, allow_nan=False) + "\n", encoding="utf-8"
            )
            target = self._root / fingerprint
            if target.exists():  # left without a manifest: not a stored solution
                shutil.rmtree(target)
            temporary.rename(target)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        self._index(manifest)
        return fingerprint

    def load(self, fingerprint: str) -> Solution:
        manifest = self._read_manifest(fingerprint)
        arrays_path = self._root / fingerprint / ARRAYS
        if _sha256(arrays_path) != manifest["checksums"][ARRAYS]:
            raise StoreError(f"solution {fingerprint}: checksum mismatch on {ARRAYS}")
        try:
            with np.load(arrays_path, allow_pickle=False) as stored:
                arrays = {name: np.array(stored[name], dtype=np.float64) for name in stored.files}
        except (OSError, ValueError) as error:
            raise StoreError(f"solution {fingerprint}: cannot read {ARRAYS}: {error}") from error

        config = config_from_data(manifest["config"])
        tree = tree_from_data(config, manifest["tree"])
        strategy: dict[str, Strategy] = {}
        offset = 0
        for node in tree:
            if not node.is_terminal:
                n_actions = len(node.actions)
                strategy[node.id] = _readonly(arrays["strategy"][offset : offset + n_actions])
                offset += n_actions

        return Solution(
            tree=tree,
            profile=profile_from_data(manifest["profile"]),
            params=params_from_data(manifest["params"]),
            iterations=int(manifest["iterations"]),
            duration_seconds=float(manifest["duration_seconds"]),
            exploitability=exploitability_from_data(manifest["exploitability"]),
            strategy=strategy,
            values=NodeValues(
                node_ids=tuple(node.id for node in tree),
                reach=_readonly(arrays["reach"]),
                opponent_mass=_readonly(arrays["opponent_mass"]),
                ev=_readonly(arrays["ev"]),
            ),
            hand_mass=_readonly(arrays["hand_mass"]),
            engine_version=str(manifest["engine_version"]),
            equity_digest=str(manifest["equity_digest"]),
        )

    def summary(self, fingerprint: str) -> SolutionSummary:
        return _summary(_summary_row(self._read_manifest(fingerprint)))

    def list_solutions(self, publishable_only: bool = False) -> list[SolutionSummary]:
        query = f"SELECT {_COLUMNS} FROM solutions"
        if publishable_only:
            query += " WHERE publishable = 1"
        query += " ORDER BY stack_btn, stack_sb, stack_bb, fingerprint"
        with closing(self._connect()) as connection:
            return [_summary(row) for row in connection.execute(query)]

    def rebuild_index(self) -> None:
        """Recreate the index from the solution directories."""
        manifests = [
            self._read_manifest(path.name)
            for path in sorted(self._root.iterdir())
            if path.is_dir()
            and not path.name.startswith(_TEMPORARY_PREFIX)
            and (path / MANIFEST).is_file()
        ]
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM solutions")
        for manifest in manifests:
            self._index(manifest)
