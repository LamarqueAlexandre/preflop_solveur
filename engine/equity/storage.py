"""Versioned on-disk storage of the equity tensors W, E3 and E2.

A tensor set is a directory holding ``w.npy``, ``e3.npy``, ``e2.npy`` and a
``manifest.json`` (format and engine versions, draws, seed, classes, SHA-256
of each file). Writing is atomic: files go to a temporary sibling directory
that replaces the target only once complete. Loading checks the format
version and the checksums, then memory-maps the arrays read-only.
"""

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from engine.equity.montecarlo import EquityTensors

FORMAT_VERSION: Final = 1
DEFAULT_DIRECTORY: Final = Path("data") / "equity"
MANIFEST: Final = "manifest.json"
FILES: Final = ("w.npy", "e3.npy", "e2.npy")


class FormatError(ValueError):
    """The stored tensors use an unsupported format version."""


class IntegrityError(ValueError):
    """A stored file is missing or does not match its checksum."""


@dataclass(frozen=True)
class EquityManifest:
    """How a stored tensor set was produced."""

    format_version: int
    engine_version: str
    n_draws: int
    seed: int
    classes: list[int] | None
    created_at: str
    duration_seconds: float
    checksums: dict[str, str]


@dataclass(frozen=True)
class StoredEquity:
    """Loaded tensors (read-only, memory-mapped) and their manifest."""

    w: NDArray[np.int32]
    e3: NDArray[np.float32]
    e2: NDArray[np.float32]
    manifest: EquityManifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save_tensors(
    directory: Path,
    w: NDArray[np.int32],
    tensors: EquityTensors,
    classes: list[int] | tuple[int, ...] | None,
    duration_seconds: float = 0.0,
) -> EquityManifest:
    """Write W, E3, E2 and their manifest to ``directory``, atomically."""
    directory = Path(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = directory.with_name(f"{directory.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    try:
        arrays = {"w.npy": w, "e3.npy": tensors.e3, "e2.npy": tensors.e2}
        for name, array in arrays.items():
            np.save(temporary / name, np.ascontiguousarray(array))
        manifest = EquityManifest(
            format_version=FORMAT_VERSION,
            engine_version=version("preflop-solveur"),
            n_draws=tensors.n_draws,
            seed=tensors.seed,
            classes=None if classes is None else sorted(int(c) for c in classes),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            duration_seconds=float(duration_seconds),
            checksums={name: _sha256(temporary / name) for name in FILES},
        )
        (temporary / MANIFEST).write_text(
            json.dumps(asdict(manifest), indent=2) + "\n", encoding="utf-8"
        )
        if directory.exists():
            backup = directory.with_name(f"{directory.name}.old-{uuid.uuid4().hex}")
            directory.rename(backup)
            temporary.rename(directory)
            shutil.rmtree(backup)
        else:
            temporary.rename(directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def read_manifest(directory: Path) -> EquityManifest:
    """Read and check the manifest of a tensor set (no checksum verification)."""
    path = Path(directory) / MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"no equity tensors in {directory} (missing {MANIFEST})")
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("format_version") != FORMAT_VERSION:
        raise FormatError(
            f"unsupported format version {content.get('format_version')!r} "
            f"(expected {FORMAT_VERSION})"
        )
    return EquityManifest(**content)


def load_tensors(directory: Path = DEFAULT_DIRECTORY, verify: bool = True) -> StoredEquity:
    """Load a tensor set; with ``verify``, check every file against its SHA-256."""
    directory = Path(directory)
    manifest = read_manifest(directory)
    for name in FILES:
        path = directory / name
        if not path.is_file():
            raise IntegrityError(f"missing file {path}")
        if verify and _sha256(path) != manifest.checksums.get(name):
            raise IntegrityError(f"checksum mismatch for {path}")
    w: NDArray[np.int32] = np.load(directory / "w.npy", mmap_mode="r")
    e3: NDArray[np.float32] = np.load(directory / "e3.npy", mmap_mode="r")
    e2: NDArray[np.float32] = np.load(directory / "e2.npy", mmap_mode="r")
    return StoredEquity(w=w, e3=e3, e2=e2, manifest=manifest)
