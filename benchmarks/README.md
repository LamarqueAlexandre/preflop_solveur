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
