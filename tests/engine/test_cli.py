"""Tests for the ``engine`` command line."""

import json
from importlib import resources
from pathlib import Path

import numpy as np
import pytest

from engine.cards import parse_class
from engine.cli import main, parse_stacks
from engine.equity import EquityTensors, compute_weights
from engine.equity.storage import load_tensors, save_tensors
from engine.library import FileSolutionStore


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


# --- engine solve ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_equity(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Full-size tensors with the real W and a made-up strength per class."""
    strengths = np.linspace(0.5, 3.0, 169)
    a, b, c = strengths[:, None, None], strengths[None, :, None], strengths[None, None, :]
    tensors = EquityTensors(
        e3=np.broadcast_to(a / (a + b + c), (169, 169, 169)).astype(np.float32),
        e2=np.broadcast_to(a / (a + b), (169, 169, 169)).astype(np.float32),
        n_draws=1,
        seed=0,
    )
    directory = tmp_path_factory.mktemp("synthetic") / "equity"
    save_tensors(directory, compute_weights(), tensors, classes=None)
    return directory


def test_solve_prints_the_convergence_and_a_summary(
    synthetic_equity: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "solve",
            "--stack",
            "5",
            "--equity",
            str(synthetic_equity),
            "--max-iterations",
            "2",
            "--check-every",
            "1",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "5bb" in out
    assert "iteration 1" in out
    assert "iteration 2" in out
    assert "NashConv" in out
    for label in ("BTN", "SB", "BB"):
        assert label in out


def test_solve_with_a_profile_file(
    synthetic_equity: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = resources.files("engine.realization").joinpath("profiles", "default.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    data["name"] = "custom"
    profile = tmp_path / "custom.json"
    profile.write_text(json.dumps(data), encoding="utf-8")
    arguments = ["solve", "--stack", "5", "--equity", str(synthetic_equity)]
    code = main([*arguments, "--profile", str(profile), "--max-iterations", "1"])
    assert code == 0
    assert "custom" in capsys.readouterr().out


def test_solve_rejects_partial_tensors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "equity"
    main(["equity", "build", "--draws", "500", "--classes", "AA,KK", "--output", str(output)])
    capsys.readouterr()
    assert main(["solve", "--stack", "5", "--equity", str(output)]) == 1
    assert "169" in capsys.readouterr().err


@pytest.mark.parametrize(
    "case", ["missing tensors", "stack below the big blind", "missing profile"]
)
def test_solve_reports_errors(
    case: str, synthetic_equity: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    options = {"--stack": "5", "--equity": str(synthetic_equity), "--max-iterations": "1"}
    if case == "missing tensors":
        options["--equity"] = str(tmp_path / "nothing")
    elif case == "stack below the big blind":
        options["--stack"] = "0.5"
    else:
        options["--profile"] = str(tmp_path / "missing.json")
    assert main(["solve", *(item for pair in options.items() for item in pair)]) == 1
    assert capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["solve"],
        ["solve", "--stack", "abc"],
        ["solve", "--stack", "5", "--max-iterations", "0"],
        ["solve", "--stack", "5", "--check-every", "-1"],
        ["solve", "--stack", "5", "--target", "0"],
    ],
)
def test_solve_invalid_arguments_are_rejected(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code != 0


# --- engine batch ------------------------------------------------------------------------


def run_batch_command(equity: Path, store: Path, *extra: str) -> int:
    arguments = ["batch", "--equity", str(equity), "--store", str(store)]
    return main([*arguments, "--max-iterations", "2", "--check-every", "1", *extra])


def test_batch_stores_each_depth_then_skips_them(
    synthetic_equity: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "solutions"
    assert run_batch_command(synthetic_equity, store, "--stacks", "3,4") == 0
    out = capsys.readouterr().out
    assert "3bb" in out and "4bb" in out
    assert "solved 2" in out
    assert len(FileSolutionStore(store).list_solutions()) == 2

    assert run_batch_command(synthetic_equity, store, "--stacks", "3-4") == 0
    out = capsys.readouterr().out
    assert out.count("already stored") == 2
    assert "skipped 2" in out


def test_batch_reports_non_conforming_solutions(
    synthetic_equity: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "solutions"
    assert run_batch_command(synthetic_equity, store, "--stacks", "20") == 0
    assert "non-conforming 1" in capsys.readouterr().out


def test_batch_rejects_partial_tensors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "equity"
    main(["equity", "build", "--draws", "500", "--classes", "AA,KK", "--output", str(output)])
    capsys.readouterr()
    assert run_batch_command(output, tmp_path / "solutions", "--stacks", "5") == 1
    assert "169" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5", [5.0]),
        ("3-5", [3.0, 4.0, 5.0]),
        ("5,12,20", [5.0, 12.0, 20.0]),
        ("3-4,10", [3.0, 4.0, 10.0]),
    ],
)
def test_stack_list_parsing(text: str, expected: list[float]) -> None:
    assert parse_stacks(text) == expected


@pytest.mark.parametrize("text", ["abc", "5-3", "0", "-2", "", "3-"])
def test_invalid_stack_lists_are_rejected(text: str) -> None:
    with pytest.raises(SystemExit) as error:
        main(["batch", "--stacks", text])
    assert error.value.code != 0
