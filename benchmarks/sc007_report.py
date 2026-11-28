"""Report of the SC-007 reference test: the BTN opens 100% at 15bb (US3, issue #28).

Run: ``uv run python benchmarks/sc007_report.py`` (needs ``data/equity`` and the
15bb solution in ``data/solutions``, see ``engine batch``).

Prints the SB strategy facing R2.0 at equilibrium and in best response, the EV
gained (D-006) and the 13x13 grids of the all-in range. The output feeds
docs/notes/sc007.md.
"""

from typing import Final

import numpy as np

from engine.best_response import exploit_solution
from engine.cards import CLASS_WEIGHTS, format_class
from engine.cards.classes import N_CLASSES, N_RANKS
from engine.equity.storage import load_tensors
from engine.game import ROOT_ID, ActionKind, Position
from engine.library import FileSolutionStore
from engine.solver import EquityTables, TerminalValues

STACK: Final = 15.0
OPEN: Final = "R2.0"
SHOVE: Final = 0.5
"""A class is drawn in the all-in grid when it shoves at least this often."""


def combos(row: np.ndarray) -> float:
    return float(CLASS_WEIGHTS @ row) / float(CLASS_WEIGHTS.sum())


def grid(frequencies: np.ndarray) -> str:
    lines = []
    for row in range(N_RANKS):
        cells = []
        for col in range(N_RANKS):
            index = row * N_RANKS + col
            cells.append(f"{format_class(index):>4}" if frequencies[index] >= SHOVE else "   ·")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def main() -> None:
    tables = EquityTables.from_stored(load_tensors(verify=False))
    store = FileSolutionStore("data/solutions")
    summary = next(s for s in store.list_solutions(publishable_only=True) if s.stacks[0] == STACK)
    solution = store.load(summary.fingerprint)
    root = solution.tree.root
    tokens = [action.token for action in root.actions]
    lock = np.zeros((len(root.actions), N_CLASSES))
    lock[tokens.index(OPEN)] = 1.0
    values = TerminalValues(solution.tree, tables, solution.profile)
    result = exploit_solution(solution, values, {ROOT_ID: lock}, Position.SB)

    btn = solution.strategy[ROOT_ID]
    print(f"## BTN à l'équilibre ({STACK:g}bb), racine")
    print(", ".join(f"{t} {combos(btn[i]):.1%}" for i, t in enumerate(tokens)))
    node = result.nodes[OPEN]
    print(f"\n## SB face à {OPEN} (fréquences sur 1326 combos)")
    for i, action in enumerate(node.actions):
        print(
            f"- {action.token} : équilibre {combos(node.equilibrium[i]):.1%}, "
            f"meilleure réponse {combos(node.best[i]):.1%}"
        )
    print(
        f"\n## EV de la SB : équilibre {result.equilibrium_ev:+.3f} bb/main, "
        f"meilleure réponse {result.value:+.3f} bb/main, EV gagnée {result.gain:+.3f} bb/main"
    )

    row = [action.kind for action in node.actions].index(ActionKind.ALL_IN)
    print(f"\n## Range d'all-in à l'équilibre (classes à ≥ {SHOVE:.0%})\n")
    print(grid(node.equilibrium[row]))
    print(f"\n## Range d'all-in en meilleure réponse (classes à ≥ {SHOVE:.0%})\n")
    print(grid(node.best[row]))
    added = [
        format_class(c)
        for c in range(N_CLASSES)
        if node.equilibrium[row][c] < SHOVE <= node.best[row][c]
    ]
    folded = [format_class(c) for c in range(N_CLASSES) if node.best[row][c] < SHOVE]
    print(f"\n## Classes ajoutées ({len(added)})\n{' '.join(added)}")
    print(f"\n## Classes qui ne font pas tapis en meilleure réponse ({len(folded)})\n")
    print(" ".join(folded))
    gains = sorted(((node.ev_gain[c], format_class(c)) for c in range(N_CLASSES)), reverse=True)
    print("\n## Plus gros gains par main face à l'open (bb)")
    print(", ".join(f"{name} {gain:+.2f}" for gain, name in gains[:8]))


if __name__ == "__main__":
    main()
