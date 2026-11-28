# Bibliothèque complète : benchmark SC-006 et certification SC-001

Note liée à SC-006, SC-001, FR-013 et US5 (issue #26). Script : `benchmarks/bench_library.py`.

## 1. Résultat

| Critère | Exigence | Mesure | Verdict |
|---|---|---|---|
| SC-006 | 23 solutions en moins de 10 h | **25 min 43 s** | OK (marge ×23) |
| SC-001 | 100 % des solutions publiées sous 0,5 % | 23/23 publiables, NashConv maximal **0,096 %** | OK |

Aucune optimisation n'est nécessaire pour SC-006.

## 2. Machine (2026-11-28)

- CPU : 13th Gen Intel Core i5-13420H, 12 cœurs logiques
- RAM : 15,7 Gio
- OS : Windows 11 (10.0.26300)
- Python 3.12.10, NumPy 2.5.5, BLAS scipy-openblas 0.3.34

## 3. Méthode

- **Paramètres** : ceux de D-014 (DCFR α = 1,5, β = 0, γ = 2) et de D-015 (contrôle toutes les 100 itérations, arrêt sous 0,1 %, au plus 2 000 itérations), avec le profil de réalisation par défaut 1.0.0.
- **Phase 1** : batch sur 5, 12 et 20bb, une profondeur par tranche. Le temps de chaque échantillon est extrapolé à sa tranche.
- **Phase 2** : batch sur la grille 3–25bb, dans le store réel `data/solutions/`. Les 3 profondeurs de la phase 1 ont été sautées : c'est l'idempotence de #25, en conditions réelles.
- **Certification SC-001** : chaque solution est **relue depuis le store**, puis son NashConv est **recalculé** à partir de la stratégie stockée, avec les vrais tenseurs. On certifie ainsi ce qui est réellement sur disque, indépendamment de la mesure faite pendant le batch.

## 4. Détail par profondeur

| Stack | Nœuds | Itérations | NashConv (manifeste) | NashConv (recalculé) | Durée |
|---|---|---|---|---|---|
| 3bb | 40 | 100 | 0,0009 % | 0,0009 % | 10 s |
| 4bb | 40 | 100 | 0,0018 % | 0,0018 % | 10 s |
| 5bb | 40 | 100 | 0,0019 % | 0,0019 % | 10 s |
| 6bb | 40 | 100 | 0,0036 % | 0,0036 % | 10 s |
| 7bb | 40 | 100 | 0,0230 % | 0,0230 % | 11 s |
| 8bb | 40 | 100 | 0,0265 % | 0,0265 % | 10 s |
| 9bb | 130 | 100 | 0,0507 % | 0,0507 % | 27 s |
| 10bb | 130 | 100 | 0,0554 % | 0,0554 % | 32 s |
| 11bb | 130 | 100 | 0,0498 % | 0,0498 % | 32 s |
| 12bb | 130 | 100 | 0,0958 % | 0,0958 % | 22 s |
| 13bb | 130 | 200 | 0,0290 % | 0,0290 % | 1 min 02 s |
| 14bb | 130 | 200 | 0,0330 % | 0,0330 % | 1 min 02 s |
| 15bb | 130 | 100 | 0,0928 % | 0,0928 % | 32 s |
| 16bb | 400 | 200 | 0,0771 % | 0,0771 % | 2 min 08 s |
| 17bb | 400 | 200 | 0,0380 % | 0,0380 % | 1 min 25 s |
| 18bb | 400 | 200 | 0,0418 % | 0,0418 % | 1 min 23 s |
| 19bb | 400 | 200 | 0,0442 % | 0,0442 % | 1 min 36 s |
| 20bb | 400 | 200 | 0,0608 % | 0,0608 % | 1 min 23 s |
| 21bb | 400 | 200 | 0,0568 % | 0,0568 % | 2 min 13 s |
| 22bb | 400 | 200 | 0,0641 % | 0,0641 % | 2 min 13 s |
| 23bb | 400 | 200 | 0,0679 % | 0,0679 % | 2 min 13 s |
| 24bb | 400 | 200 | 0,0738 % | 0,0738 % | 2 min 13 s |
| 25bb | 400 | 300 | 0,0780 % | 0,0780 % | 3 min 20 s |

**Totaux** :
- somme des temps de résolution : 25 min 36 s ;
- temps réel des deux phases : 25 min 43 s ;
- store : 36 Mo pour 23 solutions et l'index.

L'écart entre le NashConv du manifeste et le NashConv recalculé est nul (0 point). Le calcul est déterministe, et la stratégie relue est identique bit à bit à celle qui a été mesurée.

## 5. Lecture des résultats

- **L'extrapolation a sous-estimé le temps** : 17 min 25 s prévues, 25 min 43 s mesurées. Les échantillons de la phase 1 ont convergé vite : 12bb en 100 itérations, 20bb en 200. D'autres profondeurs en ont demandé davantage : 13 et 14bb ont pris 200 itérations, 25bb en a pris 300. Le nombre d'itérations, et donc la durée, varie d'une profondeur à l'autre dans une même tranche. L'écart (×1,5) reste sans conséquence face à la limite de 10 h.
- **Durée d'une itération** : environ 0,1 s à ≤ 8bb, 0,2 à 0,3 s à 9–15bb, 0,4 à 0,6 s à > 15bb. Il faut y ajouter un contrôle NashConv toutes les 100 itérations, qui coûte environ une itération. Certaines durées varient pour un même nombre d'itérations (16bb et 21–24bb à 2 min 08 s – 2 min 13 s contre 1 min 23 s pour 18bb). C'est probablement la charge de la machine et la fréquence du CPU, car le calcul lui-même est identique.
- **Convergence** : toutes les profondeurs passent sous 0,1 % en 300 itérations au plus, loin du plafond de 2 000. Le NashConv le plus élevé (0,096 % à 12bb) laisse une marge de ×5 sous le seuil de publication.
- **Ces chiffres sont relatifs au modèle.** Ils mesurent l'équilibre du jeu préflop avec réalisation d'équité (profil par défaut), pas du poker réel (principe II).

## 6. Reproduire

```bash
uv run python benchmarks/bench_library.py     # ~30 min, il faut data/equity/
```

Le store `data/solutions/` est hors git et régénérable. Relancer le script ne recalcule rien (toutes les profondeurs sont « déjà stockées »), mais refait la certification SC-001.
