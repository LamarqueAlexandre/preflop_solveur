# Benchmarks

Mesures de performance reproductibles (constitution, principe VI). Chaque benchmark utilise une graine fixe. Les résultats sont consignés ci-dessous avec la machine qui les a produits.

## Évaluateurs de mains (`bench_evaluator.py`)

```bash
uv run python benchmarks/bench_evaluator.py
```

Le benchmark tire 1 000 000 de mains de 7 cartes aléatoires (graine `20261126`) et mesure le débit de l'évaluateur rapide `evaluate_batch`, appelé sur tout le paquet en une fois. Il mesure aussi celui de l'évaluateur de référence `evaluate`, sur les 5 000 premières mains. Chaque débit est le meilleur temps sur 5 répétitions.

| Date | Machine | Python / NumPy | Rapide (mains/s) | Référence (mains/s) | Gain |
|---|---|---|---|---|---|
| 2026-11-26 | Intel Core i5-13420H, Windows 11 | 3.12.10 / 2.5.5 | 1 323 360 | 2 809 | ×471 |

## Spike des tenseurs d'équité (`spike_equity.py`, `spike_equity_numba.py`)

Issue #8. L'analyse complète se trouve dans [docs/notes/spike-equites.md](../docs/notes/spike-equites.md).

```bash
uv run python benchmarks/spike_equity.py          # partie NumPy
uv run python benchmarks/spike_equity_numba.py    # partie Numba
```

| Date | Machine | Mesure | NumPy | Numba, 1 thread | Numba, 12 threads |
|---|---|---|---|---|---|
| 2026-11-26 | Intel Core i5-13420H, Windows 11, Python 3.12.10, NumPy 2.5.5, Numba 0.68.1 | Évaluateur (mains/s) | 0,9 à 2,6 M | 9,4 M | 88,6 M |
| | | Monte-Carlo (tirages/s) | 73 800 | 3,0 M | 23,6 M |
| | | Énumération exacte d'un trio de combos | 2,12 s | 0,085 s | 0,046 s |
