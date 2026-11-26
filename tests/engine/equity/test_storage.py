"""Tests for the versioned on-disk storage of the equity tensors."""

import json
from functools import cache
from pathlib import Path

import numpy as np
import pytest
from engine.equity.storage import (
    FORMAT_VERSION,
    FormatError,
    IntegrityError,
    load_tensors,
    save_tensors,
)

from engine.cards import N_CLASSES, parse_class
from engine.equity import EquityTensors, compute_equity_tensors, compute_weights, storage

SEED = 20261126
CLASSES = tuple(parse_class(name) for name in ("AA", "KK", "AKs", "72o"))


@cache
def small_tensors() -> EquityTensors:
    return compute_equity_tensors(n_draws=2_000, seed=SEED, classes=CLASSES)


@cache
def weights() -> np.ndarray:
    return compute_weights()


def save(directory: Path) -> None:
    save_tensors(directory, weights(), small_tensors(), classes=CLASSES, duration_seconds=1.5)


# --- Round trip ------------------------------------------------------------------------


def test_round_trip_is_bit_identical(tmp_path: Path) -> None:
    save(tmp_path / "equity")
    stored = load_tensors(tmp_path / "equity")
    np.testing.assert_array_equal(stored.w, weights())
    # assert_array_equal treats NaN == NaN, so impossible cells are checked too.
    np.testing.assert_array_equal(stored.e3, small_tensors().e3)
    np.testing.assert_array_equal(stored.e2, small_tensors().e2)
    assert stored.e3.dtype == stored.e2.dtype == np.float32
    assert stored.w.dtype == np.int32
    assert stored.e3.shape == (N_CLASSES, N_CLASSES, N_CLASSES)


def test_manifest_round_trip(tmp_path: Path) -> None:
    written = save_tensors(
        tmp_path / "equity", weights(), small_tensors(), classes=CLASSES, duration_seconds=1.5
    )
    manifest = load_tensors(tmp_path / "equity").manifest
    assert manifest == written
    assert manifest.format_version == FORMAT_VERSION
    assert manifest.engine_version == "0.1.0"
    assert manifest.n_draws == 2_000
    assert manifest.seed == SEED
    assert manifest.classes == sorted(CLASSES)
    assert manifest.duration_seconds == 1.5
    assert set(manifest.checksums) == {"w.npy", "e3.npy", "e2.npy"}
    assert all(len(digest) == 64 for digest in manifest.checksums.values())


def test_all_classes_are_recorded_as_none(tmp_path: Path) -> None:
    manifest = save_tensors(tmp_path / "equity", weights(), small_tensors(), classes=None)
    assert manifest.classes is None


def test_loaded_arrays_are_read_only(tmp_path: Path) -> None:
    save(tmp_path / "equity")
    stored = load_tensors(tmp_path / "equity")
    for array in (stored.w, stored.e3, stored.e2):
        with pytest.raises(ValueError):
            array[0, 0, 0] = 0


# --- Integrity -------------------------------------------------------------------------


def test_modified_file_is_detected(tmp_path: Path) -> None:
    save(tmp_path / "equity")
    path = tmp_path / "equity" / "e3.npy"
    data = bytearray(path.read_bytes())
    data[-1] ^= 0xFF  # flip the bits of the last byte
    path.write_bytes(bytes(data))
    with pytest.raises(IntegrityError):
        load_tensors(tmp_path / "equity")


def test_missing_file_is_detected(tmp_path: Path) -> None:
    save(tmp_path / "equity")
    (tmp_path / "equity" / "e2.npy").unlink()
    with pytest.raises(IntegrityError):
        load_tensors(tmp_path / "equity")


def test_missing_directory_is_detected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_tensors(tmp_path / "nothing")


def test_other_format_version_is_rejected(tmp_path: Path) -> None:
    save(tmp_path / "equity")
    manifest_path = tmp_path / "equity" / "manifest.json"
    content = json.loads(manifest_path.read_text(encoding="utf-8"))
    content["format_version"] = FORMAT_VERSION + 1
    manifest_path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(FormatError):
        load_tensors(tmp_path / "equity")


# --- Atomic write ------------------------------------------------------------------------


def test_failed_save_keeps_the_previous_tensors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save(tmp_path / "equity")
    before = load_tensors(tmp_path / "equity").manifest

    def broken_save(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(storage.np, "save", broken_save)
    with pytest.raises(OSError):
        save(tmp_path / "equity")
    monkeypatch.undo()

    assert load_tensors(tmp_path / "equity").manifest == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["equity"]  # no leftovers


def test_save_replaces_existing_tensors(tmp_path: Path) -> None:
    save(tmp_path / "equity")
    other = compute_equity_tensors(n_draws=1_000, seed=SEED + 1, classes=CLASSES)
    save_tensors(tmp_path / "equity", weights(), other, classes=CLASSES)
    stored = load_tensors(tmp_path / "equity")
    assert stored.manifest.seed == SEED + 1
    np.testing.assert_array_equal(stored.e3, other.e3)


# --- Reproducibility (principle III) -------------------------------------------------------


def test_same_seed_gives_same_checksums(tmp_path: Path) -> None:
    first = save_tensors(
        tmp_path / "a",
        weights(),
        compute_equity_tensors(n_draws=2_000, seed=SEED, classes=CLASSES),
        classes=CLASSES,
    )
    second = save_tensors(
        tmp_path / "b",
        weights(),
        compute_equity_tensors(n_draws=2_000, seed=SEED, classes=CLASSES),
        classes=CLASSES,
    )
    assert first.checksums == second.checksums
