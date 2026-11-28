"""SC-006 benchmark: generate the full library and certify it (SC-001), issue #26.

Run: ``uv run python benchmarks/bench_library.py`` (needs ``data/equity``).

1. Machine: CPU, logical cores, RAM, OS, Python, NumPy and its BLAS.
2. Phase 1: batch on one depth per tranche (5, 12, 20bb), extrapolated to the grid.
3. Phase 2: batch on the whole grid (3-25bb); the phase 1 depths are skipped.
4. SC-001: every stored solution is read back and its NashConv recomputed from
   the stored strategy, then compared with the manifest and the 0.5% threshold.

Solutions go to the real store ``data/solutions`` (D-016), read later by the API.
Results are recorded in ``benchmarks/README.md`` and docs/notes/bibliotheque-sc006.md.
"""

import ctypes
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Final

import numpy as np

from engine.equity.storage import load_tensors
from engine.game import build_tree
from engine.game.config import STACK_GRID, GameConfig, Tranche
from engine.library import (
    BatchEvent,
    ConvergenceChecked,
    DepthStarted,
    FileSolutionStore,
    SolveParams,
    run_batch,
)
from engine.realization import default_profile
from engine.solver import (
    PUBLICATION_THRESHOLD_PERCENT,
    EquityTables,
    TerminalValues,
    exploitability,
)

STORE: Final = Path("data") / "solutions"
SAMPLES: Final = (5.0, 12.0, 20.0)
"""One depth per tranche (<= 8bb, 9-15bb, > 15bb)."""
SC006_LIMIT_HOURS: Final = 10.0


def _cpu_name() -> str:
    if sys.platform == "win32":
        import winreg

        key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            return str(winreg.QueryValueEx(handle, "ProcessorNameString")[0]).strip()
    return platform.processor() or "unknown"


def _ram_gib() -> float:
    if sys.platform != "win32":
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
    return float(status.total_physical) / 2**30


def _blas() -> str:
    config: Any = np.show_config(mode="dicts")
    blas = config.get("Build Dependencies", {}).get("blas", {})
    return f"{blas.get('name', '?')} {blas.get('version', '')}".strip()


def machine() -> None:
    print("## Machine")
    print(f"- CPU : {_cpu_name()}, {os.cpu_count()} cœurs logiques")
    print(f"- RAM : {_ram_gib():.1f} Gio")
    print(f"- OS : {platform.platform()}")
    print(f"- Python {platform.python_version()}, NumPy {np.__version__}, BLAS {_blas()}")
    print()


def _on_event(event: BatchEvent) -> None:
    if isinstance(event, DepthStarted):
        state = "déjà stockée" if event.already_stored else "résolution"
        print(f"  [{event.index}/{event.total}] {event.config.stacks[0]:g}bb : {state}", flush=True)
    elif isinstance(event, ConvergenceChecked):
        print(
            f"      {event.iterations} it. : NashConv {event.exploitability.percent:.4f} %",
            flush=True,
        )


def _duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs:02d} s" if minutes else f"{secs} s"


def main() -> None:
    machine()
    tables = EquityTables.from_stored(load_tensors())
    profile = default_profile()
    params = SolveParams()
    store = FileSolutionStore(STORE)

    print("## Phase 1 : une profondeur par tranche")
    start = time.perf_counter()
    sample = run_batch(
        [GameConfig.equal_stacks(s) for s in SAMPLES], tables, profile, store, params, _on_event
    )
    phase1 = time.perf_counter() - start
    per_tranche: dict[Tranche, float] = {}
    for entry in sample.entries:
        stored = store.load(entry.summary.fingerprint)
        per_tranche[entry.config.tranche] = stored.duration_seconds
    estimate = sum(per_tranche[GameConfig.equal_stacks(s).tranche] for s in STACK_GRID)
    for tranche, seconds in per_tranche.items():
        print(f"- {tranche.value} : {_duration(seconds)} par profondeur")
    print(f"- Extrapolation à la grille ({len(STACK_GRID)} profondeurs) : {_duration(estimate)}")
    print()

    print("## Phase 2 : grille complète")
    start = time.perf_counter()
    report = run_batch(
        [GameConfig.equal_stacks(s) for s in STACK_GRID], tables, profile, store, params, _on_event
    )
    phase2 = time.perf_counter() - start
    print()

    print("## Résultats et vérification SC-001 (NashConv recalculé depuis le store)")
    print()
    columns = ("Stack", "Nœuds", "Itérations", "NashConv (manifeste)", "NashConv (recalculé)")
    print("| " + " | ".join((*columns, "Durée", "Statut")) + " |")
    print("|---|---|---|---|---|---|---|")
    total = 0.0
    worst = 0.0
    largest_gap = 0.0
    failures = 0
    for entry in report.entries:
        solution = store.load(entry.summary.fingerprint)
        tree = build_tree(solution.config)
        values = TerminalValues(tree, tables, solution.profile)
        recomputed = exploitability(tree, values, solution.strategy).percent
        stored = solution.exploitability.percent
        largest_gap = max(largest_gap, abs(recomputed - stored))
        publishable = recomputed < PUBLICATION_THRESHOLD_PERCENT and solution.publishable
        if solution.publishable:
            worst = max(worst, recomputed)
        failures += not publishable
        total += solution.duration_seconds
        status = "publiable" if publishable else "NON CONFORME"
        print(
            f"| {solution.config.stacks[0]:g}bb | {len(tree)} | {solution.iterations} "
            f"| {stored:.4f} % | {recomputed:.4f} % | {_duration(solution.duration_seconds)} "
            f"| {status} |",
            flush=True,
        )
    print()
    print(f"- Somme des temps de résolution : {_duration(total)} ({total / 3600:.2f} h)")
    print(f"- Temps réel des deux phases : {_duration(phase1 + phase2)}")
    print(f"- Extrapolation de la phase 1 : {_duration(estimate)}")
    verdict = "OK" if total / 3600 < SC006_LIMIT_HOURS else "DÉPASSÉ"
    print(f"- SC-006 (< {SC006_LIMIT_HOURS:g} h) : {verdict}")
    print(
        f"- SC-001 : NashConv maximal des solutions publiées {worst:.4f} % "
        f"(seuil {PUBLICATION_THRESHOLD_PERCENT} %), non conformes : {failures}"
    )
    print(f"- Écart maximal manifeste / recalcul : {largest_gap:.2e} point")
    print("- Exploitabilité relative au modèle (profil de réalisation par défaut).")


if __name__ == "__main__":
    main()
