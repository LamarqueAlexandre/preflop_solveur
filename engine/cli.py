"""The ``engine`` command line.

engine equity build [--draws N] [--seed S] [--classes AA,KK,...] [--output DIR]
engine equity info [--path DIR]
engine solve --stack S [--max-iterations N] [--target P] [--check-every K]
             [--equity DIR] [--profile FILE]
engine batch [--stacks 3-25] [--store DIR] [--max-iterations N] [--target P]
             [--check-every K] [--equity DIR] [--profile FILE]
engine sensitivity [--stacks 5,12,20] [--modes U+,U-,E+,E-] [--delta 0.1]
                   [--base-store DIR] [--store DIR] [--output FILE] [solving options]
"""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from engine.cards import CLASS_WEIGHTS, format_class, parse_class
from engine.equity import N_DRAWS, compute_equity_tensors, compute_weights
from engine.equity.storage import (
    DEFAULT_DIRECTORY,
    FormatError,
    IntegrityError,
    load_tensors,
    read_manifest,
    save_tensors,
)
from engine.game import ROOT_ID, GameConfig, Position, build_tree
from engine.game.config import STACK_GRID
from engine.library import (
    BatchEvent,
    BatchReport,
    BatchStatus,
    ConvergenceChecked,
    DepthStarted,
    FileSolutionStore,
    Solution,
    SolveParams,
    run_batch,
    solve,
)
from engine.library.sensitivity import MODES, render_report, run_sensitivity
from engine.realization import ProfileError, RealizationProfile, default_profile, load_profile
from engine.solver import EquityTables, Exploitability

DEFAULT_SEED = 20261126
DEFAULT_STORE = Path("data") / "solutions"
DEFAULT_SENSITIVITY_STORE = Path("data") / "sensitivity"


def _positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return value


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a number, got {text}") from None
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be positive, got {text}")
    return value


def parse_stacks(text: str) -> list[float]:
    """Stack list such as ``5``, ``3-25`` (1bb steps) or ``3-5,10,12``."""
    stacks: list[float] = []
    for item in text.split(","):
        bounds = [bound.strip() for bound in item.split("-")]
        if len(bounds) > 2 or not all(bounds):
            raise ValueError(f"invalid stack or range {item.strip()!r}")
        low, high = float(bounds[0]), float(bounds[-1])
        if not 0 < low <= high:
            raise ValueError(f"invalid stack or range {item.strip()!r}")
        stacks.extend(low + step for step in range(int(high - low) + 1))
    return stacks


def _stack_list(text: str) -> list[float]:
    try:
        return parse_stacks(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _mode_list(text: str) -> list[str]:
    modes = [mode.strip() for mode in text.split(",")]
    unknown = [mode for mode in modes if mode not in MODES]
    if not modes or unknown:
        raise argparse.ArgumentTypeError(f"modes must be among {', '.join(MODES)}, got {text!r}")
    return modes


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


def _print_summary(solution: Solution) -> None:
    result = solution.exploitability
    status = "publishable" if solution.publishable else "NOT publishable"
    print(f"Done: {solution.iterations} iterations in {_duration(solution.duration_seconds)}")
    print(f"  NashConv       : {result.percent:.4f}% of the starting pot ({status})")
    for position, gain, ev in zip(Position, result.gains, solution.root_ev(), strict=True):
        print(f"  {position.name:<3} EV {ev:+.4f}bb, best-response gain {gain:.6f}bb")
    root = solution.node(ROOT_ID)
    frequencies = root.strategy @ CLASS_WEIGHTS / float(CLASS_WEIGHTS.sum())
    played = ", ".join(
        f"{action.token} {frequency:.1%}"
        for action, frequency in zip(root.actions, frequencies, strict=True)
    )
    print(f"  {root.actor.name} at the root: {played}")
    print("  (EVs and exploitability are relative to the model and its realization profile)")


def _load_inputs(
    args: argparse.Namespace, stacks: Sequence[float]
) -> tuple[RealizationProfile, list[GameConfig], EquityTables] | None:
    """Profile, configurations and full equity tables; None (and a message) on error."""
    try:
        profile = default_profile() if args.profile is None else load_profile(args.profile)
        configs = [
            GameConfig.equal_stacks(stack, realization_profile=profile.name) for stack in stacks
        ]
        if read_manifest(args.equity).classes is not None:
            print(
                f"{args.equity} holds partial tensors: all 169 classes are needed", file=sys.stderr
            )
            return None
        tables = EquityTables.from_stored(load_tensors(args.equity))
    except (ProfileError, ValueError, FileNotFoundError) as error:
        print(f"Cannot solve: {error}", file=sys.stderr)
        return None
    return profile, configs, tables


def _params(args: argparse.Namespace) -> SolveParams:
    return SolveParams(
        max_iterations=args.max_iterations,
        target_percent=args.target,
        check_every=args.check_every,
    )


def _solve(args: argparse.Namespace) -> int:
    inputs = _load_inputs(args, [args.stack])
    if inputs is None:
        return 1
    profile, configs, tables = inputs
    tree = build_tree(configs[0])
    params = _params(args)
    print(
        f"Solving {args.stack:g}bb ({len(tree)} nodes), profile {profile.name} {profile.version}, "
        f"target NashConv < {params.target_percent}%, at most {params.max_iterations} iterations"
    )
    start = time.perf_counter()

    def progress(iterations: int, result: Exploitability) -> None:
        elapsed = _duration(time.perf_counter() - start)
        print(f"  iteration {iterations}: NashConv {result.percent:.4f}% ({elapsed})", flush=True)

    _print_summary(solve(tree, tables, profile, params, progress))
    return 0


def _print_batch_event(event: BatchEvent) -> None:
    if isinstance(event, DepthStarted):
        label = f"[{event.index}/{event.total}] {event.config.stacks[0]:g}bb"
        state = "already stored" if event.already_stored else "solving"
        print(f"{label}: {state} ({event.fingerprint[:12]})", flush=True)
    elif isinstance(event, ConvergenceChecked):
        percent = event.exploitability.percent
        print(f"    iteration {event.iterations}: NashConv {percent:.4f}%", flush=True)
    elif event.entry.status is BatchStatus.SOLVED:
        summary = event.entry.summary
        status = "publishable" if summary.publishable else "NON-CONFORMING (not published)"
        print(
            f"    done: {summary.iterations} iterations, NashConv "
            f"{summary.nash_conv_percent:.4f}%, {_duration(event.entry.seconds)}, {status}",
            flush=True,
        )


def _print_batch_report(report: BatchReport, store: Path) -> None:
    print(
        f"Batch done in {_duration(report.seconds)}: solved {report.solved}, "
        f"skipped {report.skipped}, non-conforming {len(report.non_conforming)}"
    )
    for entry in report.non_conforming:
        summary = entry.summary
        print(
            f"  non-conforming: {summary.stacks[0]:g}bb, NashConv "
            f"{summary.nash_conv_percent:.4f}% after {summary.iterations} iterations "
            "(retry with other convergence parameters, e.g. a larger --max-iterations)"
        )
    print(f"  store: {store}")
    print("  (exploitability is relative to the model and its realization profile)")


def _batch(args: argparse.Namespace) -> int:
    inputs = _load_inputs(args, args.stacks)
    if inputs is None:
        return 1
    profile, configs, tables = inputs
    params = _params(args)
    print(
        f"Batch of {len(configs)} depths, profile {profile.name} {profile.version}, "
        f"target NashConv < {params.target_percent}%, at most {params.max_iterations} "
        f"iterations, store {args.store}"
    )
    store = FileSolutionStore(args.store)
    report = run_batch(configs, tables, profile, store, params, _print_batch_event)
    _print_batch_report(report, args.store)
    return 0


def _sensitivity(args: argparse.Namespace) -> int:
    inputs = _load_inputs(args, args.stacks)
    if inputs is None:
        return 1
    profile, _, tables = inputs
    print(
        f"Sensitivity of {', '.join(f'{s:g}bb' for s in args.stacks)} to profile "
        f"{profile.name} {profile.version}: modes {', '.join(args.modes)}, delta {args.delta:g}"
    )
    results = run_sensitivity(
        args.stacks,
        args.modes,
        args.delta,
        tables,
        profile,
        _params(args),
        FileSolutionStore(args.base_store),
        FileSolutionStore(args.store),
        _print_batch_event,
    )
    report = render_report(results, format_class)
    print()
    print(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
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

    solve_parser = commands.add_parser("solve", help="solve the full tree of one depth")
    solve_parser.add_argument(
        "--stack", type=_positive_float, required=True, help="equal stacks, in bb"
    )
    _add_solving_options(solve_parser)
    solve_parser.set_defaults(handler=_solve)

    batch_parser = commands.add_parser("batch", help="solve and store the depths of the grid")
    batch_parser.add_argument(
        "--stacks",
        type=_stack_list,
        default=list(STACK_GRID),
        help=f"depths, e.g. 5,12,20 or 3-8 (default: {STACK_GRID[0]:g}-{STACK_GRID[-1]:g})",
    )
    batch_parser.add_argument(
        "--store", type=Path, default=DEFAULT_STORE, help="solution store directory"
    )
    _add_solving_options(batch_parser)
    batch_parser.set_defaults(handler=_batch)

    sensitivity = commands.add_parser(
        "sensitivity", help="compare the equilibrium under variants of the realization profile"
    )
    sensitivity.add_argument(
        "--stacks", type=_stack_list, default=[5.0, 12.0, 20.0], help="depths (default: 5,12,20)"
    )
    sensitivity.add_argument(
        "--modes", type=_mode_list, default=list(MODES), help=f"among {','.join(MODES)}"
    )
    sensitivity.add_argument(
        "--delta", type=_positive_float, default=0.1, help="factor variation (default 0.1)"
    )
    sensitivity.add_argument(
        "--base-store", type=Path, default=DEFAULT_STORE, help="store of the base solutions"
    )
    sensitivity.add_argument(
        "--store", type=Path, default=DEFAULT_SENSITIVITY_STORE, help="store of the variants"
    )
    sensitivity.add_argument("--output", type=Path, default=None, help="Markdown report file")
    _add_solving_options(sensitivity)
    sensitivity.set_defaults(handler=_sensitivity)
    return parser


def _add_solving_options(parser: argparse.ArgumentParser) -> None:
    defaults = SolveParams()
    parser.add_argument("--max-iterations", type=_positive_int, default=defaults.max_iterations)
    parser.add_argument(
        "--target",
        type=_positive_float,
        default=defaults.target_percent,
        help="stop below this NashConv, in %% of the starting pot",
    )
    parser.add_argument(
        "--check-every",
        type=_positive_int,
        default=defaults.check_every,
        help="iterations between two NashConv checks",
    )
    parser.add_argument(
        "--equity", type=Path, default=DEFAULT_DIRECTORY, help="equity tensor directory"
    )
    parser.add_argument(
        "--profile", type=Path, default=None, help="realization profile file (default: built-in)"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``engine`` command; returns the exit code."""
    args = _parser().parse_args(argv)
    result: int = args.handler(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
