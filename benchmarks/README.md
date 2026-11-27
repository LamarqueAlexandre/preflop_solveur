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

## Valeurs terminales (`bench_terminal.py`)

Issue #18. Il faut les tenseurs d'équité dans `data/equity/`.

```bash
uv run python benchmarks/bench_terminal.py
```

Le benchmark mesure un appel `TerminalValues.values` sur les vrais tenseurs (169 classes), pour chaque type de terminal de l'arbre 20bb, avec des reaches aléatoires (graine `20261127`). Il mesure aussi le cache des tenseurs de parts du flop et une passe complète (tous les terminaux, pour les 3 joueurs). Chaque temps est le meilleur sur 20 répétitions (3 pour la passe complète).

**Optimisation mesurée.** Une contraction `np.einsum` à trois opérandes prenait 12,8 ms par appel. Chaque contraction est maintenant écrite comme un produit matrice-vecteur sur le tenseur aplati (C-contigu, sans copie), soit 1,6 à 2,5 ms. Les parts du flop du dernier joueur vivant se déduisent des autres (leur somme vaut W) : le cache passe de 25 à 14 tenseurs.

| Date | Machine | Python / NumPy | Fold | Showdown 3j | Showdown 2j | Flop 2j | Flop 3j | Cache flop (20bb) | Passe complète (20bb) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-27 | Intel Core i5-13420H, Windows 11 | 3.12.10 / 2.5.5 | 1,7 ms | 5,7 ms | 6,1 ms | 3,9 ms | 4,0 ms | 14 tenseurs, 541 Mo | 3,6 s |

## Itération du Discounted CFR (`bench_cfr.py`)

Issue #19. Il faut les tenseurs d'équité dans `data/equity/`.

```bash
uv run python benchmarks/bench_cfr.py
```

Pour les arbres 8, 12 et 20bb, le benchmark compare l'évaluation de tous les terminaux pour les 3 joueurs, un par un (`values`) et par lots (`values_batch`), avec des reaches aléatoires (graine `20261127`). Il mesure aussi une itération complète de DCFR (moyenne de 5 itérations après une itération de chauffe).

**Optimisation mesurée.** Les terminaux qui partagent un tenseur sont évalués en un seul produit matrice-matrice : le tenseur (39 Mo) est lu une fois pour tous au lieu d'une fois par terminal. Le profilage montre que presque tout le temps restant est passé dans ces produits (BLAS).

| Date | Machine | Python / NumPy | Arbre | Terminaux × 3, un par un | Par lots | Itération DCFR |
|---|---|---|---|---|---|---|
| 2026-11-27 | Intel Core i5-13420H, Windows 11 | 3.12.10 / 2.5.5 | 8bb (22 terminaux) | 0,49 s | 0,15 s | 0,12 s |
| | | | 12bb (76 terminaux) | 1,33 s | 0,29 s | 0,22 s |
| | | | 20bb (238 terminaux) | 3,88 s | 0,64 s | 0,45 s |
