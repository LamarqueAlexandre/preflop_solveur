"""Tests for the ``engine`` command line."""

from pathlib import Path

import numpy as np
import pytest

from engine.cards import parse_class
from engine.cli import main
from engine.equity.storage import load_tensors


def test_equity_build_on_a_subset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "equity"
    code = main(
        [
            "equity",
            "build",
            "--draws",
            "1000",
            "--seed",
            "7",
            "--classes",
            "AA,KK,AKs",
            "--output",
            str(output),
        ]
    )
    assert code == 0
    stored = load_tensors(output)
    assert stored.manifest.n_draws == 1000
    assert stored.manifest.seed == 7
    assert stored.manifest.classes == sorted(parse_class(c) for c in ("AA", "KK", "AKs"))
    aa, kk = parse_class("AA"), parse_class("KK")
    assert not np.isnan(stored.e3[aa, kk, kk])
    assert str(output) in capsys.readouterr().out


def test_equity_info_prints_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "equity"
    main(["equity", "build", "--draws", "500", "--classes", "AA,KK", "--output", str(output)])
    capsys.readouterr()
    assert main(["equity", "info", "--path", str(output)]) == 0
    out = capsys.readouterr().out
    assert "500" in out
    assert "OK" in out


def test_equity_info_reports_corruption(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "equity"
    main(["equity", "build", "--draws", "500", "--classes", "AA,KK", "--output", str(output)])
    (output / "w.npy").write_bytes(b"corrupted")
    capsys.readouterr()
    assert main(["equity", "info", "--path", str(output)]) == 1
    assert "integrity" in capsys.readouterr().err.lower()


def test_equity_info_on_a_missing_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["equity", "info", "--path", str(tmp_path / "nothing")]) == 1
    assert capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["equity", "build", "--draws", "0"],
        ["equity", "build", "--draws", "-5"],
        ["equity", "build", "--classes", "AA,XYZ"],
        ["equity"],
        [],
    ],
)
def test_invalid_arguments_are_rejected(arguments: list[str], tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main([*arguments, "--output", str(tmp_path / "x")] if "build" in arguments else arguments)
    assert error.value.code != 0
