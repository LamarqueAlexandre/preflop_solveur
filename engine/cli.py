"""The ``engine`` command line.

engine equity build [--draws N] [--seed S] [--classes AA,KK,...] [--output DIR]
engine equity info [--path DIR]
"""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from engine.cards import format_class, parse_class
from engine.equity import N_DRAWS, compute_equity_tensors, compute_weights
from engine.equity.storage import (
    DEFAULT_DIRECTORY,
    FormatError,
    IntegrityError,
    load_tensors,
    save_tensors,
)

DEFAULT_SEED = 20261126


def _positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return value


def _class_list(text: str) -> list[int]:
    try:
        return [parse_class(name.strip()) for name in text.split(",") if name.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s"


def _build(args: argparse.Namespace) -> int:
    classes: list[int] | None = args.classes
    label = "all 169 classes" if classes is None else ", ".join(format_class(c) for c in classes)
    print(f"Building equity tensors: {args.draws:,} draws per triplet, seed {args.seed}, {label}")
    start = time.perf_counter()

    def progress(done: int, total: int) -> None:
        elapsed = time.perf_counter() - start
        remaining = elapsed / done * (total - done)
        print(
            f"\r  {done:,}/{total:,} triplets ({done / total:.1%}), "
            f"elapsed {_duration(elapsed)}, remaining ~{_duration(remaining)}",
            end="",
            flush=True,
        )

    weights = compute_weights()
    tensors = compute_equity_tensors(
        n_draws=args.draws, seed=args.seed, classes=classes, progress=progress
    )
    duration = time.perf_counter() - start
    print()
    save_tensors(args.output, weights, tensors, classes=classes, duration_seconds=duration)
    print(f"Saved to {args.output} in {_duration(duration)}")
    return 0


def _info(args: argparse.Namespace) -> int:
    try:
        stored = load_tensors(args.path)
    except IntegrityError as error:
        print(f"Integrity check failed: {error}", file=sys.stderr)
        return 1
    except (FileNotFoundError, FormatError) as error:
        print(f"Cannot read equity tensors: {error}", file=sys.stderr)
        return 1
    manifest = stored.manifest
    classes = (
        "all 169"
        if manifest.classes is None
        else ", ".join(format_class(c) for c in manifest.classes)
    )
    print(f"Equity tensors in {args.path}")
    print(f"  format version : {manifest.format_version}")
    print(f"  engine version : {manifest.engine_version}")
    print(f"  draws/triplet  : {manifest.n_draws:,}")
    print(f"  seed           : {manifest.seed}")
    print(f"  classes        : {classes}")
    print(f"  created at     : {manifest.created_at}")
    print(f"  build time     : {_duration(manifest.duration_seconds)}")
    print("  integrity      : OK (SHA-256 checked)")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine", description="Expresso 3-max preflop engine.")
    commands = parser.add_subparsers(dest="command", required=True)

    equity = commands.add_parser("equity", help="equity tensors W, E3, E2")
    equity_commands = equity.add_subparsers(dest="action", required=True)

    build = equity_commands.add_parser("build", help="compute and store the tensors")
    build.add_argument("--draws", type=_positive_int, default=N_DRAWS, help="draws per triplet")
    build.add_argument("--seed", type=int, default=DEFAULT_SEED, help="global seed")
    build.add_argument(
        "--classes", type=_class_list, default=None, help="subset, e.g. AA,KK,AKs (default: all)"
    )
    build.add_argument("--output", type=Path, default=DEFAULT_DIRECTORY, help="target directory")
    build.set_defaults(handler=_build)

    info = equity_commands.add_parser("info", help="show the manifest and check integrity")
    info.add_argument("--path", type=Path, default=DEFAULT_DIRECTORY, help="tensor directory")
    info.set_defaults(handler=_info)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``engine`` command; returns the exit code."""
    args = _parser().parse_args(argv)
    result: int = args.handler(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
