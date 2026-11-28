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

## Convergence de DCFR mesurée par NashConv (`convergence_nashconv.py`)

Issue #20. Il faut les tenseurs d'équité dans `data/equity/`. Durée : environ 18 minutes.

```bash
uv run python benchmarks/convergence_nashconv.py
```

Le script lance DCFR (paramètres de D-014, profil de réalisation par défaut) et calcule NashConv (D-001) de la stratégie moyenne à 50, 100, 200, 500 et 1 000 itérations. NashConv est exprimé en % du pot de départ (1,5bb). Le seuil de publication est de 0,5 %. Le calcul de NashConv coûte 0,1 à 0,7 s.

| Date | Machine | Arbre | 50 it. | 100 it. | 200 it. | 500 it. | 1 000 it. | Temps pour 1 000 it. |
|---|---|---|---|---|---|---|---|---|
| 2026-11-27 | Intel Core i5-13420H, Windows 11, Python 3.12.10, NumPy 2.5.5 | 8bb | 0,094 % | 0,027 % | 0,0075 % | 0,0014 % | 0,0003 % | 90 s |
| | | 12bb | 0,40 % | 0,096 % | 0,020 % | 0,0035 % | 0,0009 % | 286 s |
| | | 20bb | 1,28 % | 0,27 % | 0,061 % | 0,0090 % | 0,0024 % | 641 s |

Le seuil de 0,5 % est atteint en moins de 100 itérations à 20bb, soit environ 1 minute. NashConv est divisé par environ 4 quand le nombre d'itérations double. La décroissance est donc proche de 1/T², bien plus rapide que la borne théorique en 1/√T.

## Bibliothèque complète, SC-006 et SC-001 (`bench_library.py`)

Issue #26. Il faut les tenseurs d'équité dans `data/equity/`. Durée : environ 30 minutes. Le rapport complet se trouve dans [docs/notes/bibliotheque-sc006.md](../docs/notes/bibliotheque-sc006.md).

```bash
uv run python benchmarks/bench_library.py
```

Le script relève la machine, résout une profondeur par tranche et extrapole, puis lance le batch sur la grille 3–25bb dans `data/solutions/`. Il relit ensuite chaque solution et recalcule son NashConv à partir de la stratégie stockée (SC-001). Paramètres : D-014, D-015, profil par défaut 1.0.0.

| Date | Machine | Python / NumPy / BLAS | Extrapolation | Durée totale (23 solutions) | Itérations | NashConv max | Non conformes |
|---|---|---|---|---|---|---|---|
| 2026-11-28 | Intel Core i5-13420H (12 cœurs logiques), 15,7 Gio, Windows 11 | 3.12.10 / 2.5.5 / scipy-openblas 0.3.34 | 17 min 25 s | 25 min 43 s (limite 10 h) | 100 à 300 | 0,096 % | 0 |

## Meilleure réponse contre vilains verrouillés (`bench_best_response.py`)

Issue #27. Il faut les tenseurs d'équité dans `data/equity/` et la bibliothèque dans `data/solutions/` (`engine batch`).

```bash
uv run python benchmarks/bench_best_response.py
```

Héros SB. Le nœud racine du BTN est verrouillé soit sur son équilibre (verrouillage neutre), soit sur sa plus grosse action sous l'all-in, jouée avec 100 % des mains. « À froid » inclut la construction des valeurs terminales de la solution (cache des parts au flop). « À chaud » les réutilise (meilleur de 3 essais). SC-005 exige moins de 5 s, l'objectif est moins de 1 s.

| Date | Machine | Python / NumPy | Profondeur | À froid | À chaud | EV gagnée SB (verrouillage 100 %) |
|---|---|---|---|---|---|---|
| 2026-11-28 | Intel Core i5-13420H, Windows 11 | 3.12.10 / 2.5.5 | 5bb (C 100 %) | 0,48 s | 0,045 s | +0,147 bb/main |
| | | | 12bb (R2.0 100 %) | 1,06 s | 0,132 s | +0,705 bb/main |
| | | | 20bb (R2.5 100 %) | 1,93 s | 0,272 s | +1,331 bb/main |
| | | | 25bb (R2.5 100 %) | 1,91 s | 0,257 s | +1,538 bb/main |

Avec un verrouillage neutre (BTN à l'équilibre), l'EV gagnée vaut 0 à 0,0006 bb/main : c'est le terme de la SB dans NashConv.
