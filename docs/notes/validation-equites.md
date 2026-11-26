# Validation D-003 des équités Monte-Carlo

Issue #11, lot 2. Exigences liées : SC-003, D-003, D-010.

## Protocole

- **1 000 trios** de classes triés (a ≤ b ≤ c), tous distincts et possibles (W > 0), tirés uniformément parmi les 818 532 trios possibles.
- Équités Monte-Carlo avec **450 000 tirages par trio** (`N_DRAWS`, D-010). Les graines par trio sont les mêmes que celles du calcul des tenseurs complets : on valide donc exactement les valeurs qui seront stockées.
- Référence : l'**énumération exhaustive** de #10 (tous les boards, avec réduction par symétries de couleurs).
- Écart = Monte-Carlo − exact, en points de pourcentage, pour les 3 valeurs E₃ et les 3 valeurs E₂ de chaque trio, soit 3 000 valeurs de chaque type.
- Graine `20261126`. Commande : `uv run python benchmarks/validate_equity.py`.
- Machine : Intel Core i5-13420H (12 threads), Windows 11, Python 3.12.10, NumPy 2.5.5, Numba 0.68.1. Durée : **811 s**, presque entièrement consacrée à la référence exacte.

## Résultats

| | Écart moyen | Médiane | 90ᵉ centile | 99ᵉ centile | Écart maximal |
|---|---|---|---|---|---|
| **E₃** | **0,051** | 0,043 | 0,107 | 0,170 | **0,257** |
| E₂ (troisième main morte) | 0,053 | 0,045 | 0,111 | 0,177 | 0,292 |

**D-003 (E₃) : écart moyen 0,051 < 0,1 et écart maximal 0,257 < 0,3 → conforme.**

E₂ respecte aussi les deux seuils, bien que D-003 ne porte que sur E₃.

### Répartition des écarts absolus (3 000 valeurs chacun)

| Écart (points) | E₃ | E₂ |
|---|---|---|
| [0,00 ; 0,05) | 1 686 | 1 646 |
| [0,05 ; 0,10) | 948 | 928 |
| [0,10 ; 0,15) | 299 | 343 |
| [0,15 ; 0,20) | 59 | 76 |
| [0,20 ; 0,25) | 6 | 5 |
| [0,25 ; 0,30) | 2 | 2 |
| ≥ 0,30 | 0 | 0 |

### Les 5 trios les plus éloignés (E₃)

| Trio | Écarts des 3 joueurs (points) |
|---|---|
| A4s / 95s / K2o | +0,257 / −0,144 / −0,113 |
| Q9s / Q9o / T8o | −0,105 / −0,151 / +0,256 |
| K7s / T9s / 42o | +0,221 / −0,132 / −0,089 |
| Q5s / 94s / T3o | −0,206 / −0,007 / +0,213 |
| T9o / T4o / K2o | −0,093 / −0,116 / +0,208 |

Aucun motif particulier : ce sont des trios ordinaires, tombés par hasard dans la queue de la distribution.

## Lecture

**L'écart moyen correspond à la théorie.** Le spike (#8) prévoyait un écart moyen de √(2/π) × σ / √n. Avec σ ≈ 0,436 et n = 450 000, cela donne 0,8 × 0,436 / 671 ≈ **0,052 point**. On mesure 0,051.

**L'écart maximal reste sous le seuil, avec peu de marge.** Le calibrage visait 95 % de chances que les 3 000 valeurs restent toutes sous 0,3 point. Le maximum observé (0,257) est cohérent avec ce calibrage. Il y avait environ 5 % de risque d'un dépassement par simple malchance : dans ce cas, le résultat aurait été rapporté tel quel, sans changer de graine.

**Sur le tenseur entier** (2,5 millions de valeurs E₃), on attend de 10 à 130 valeurs au-delà de 0,3 point (spike, § 7). D-003 est jugé sur un échantillon, et l'écart moyen reste environ deux fois sous le seuil.
