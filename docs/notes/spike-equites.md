# Spike #8 — Coût des tenseurs d'équité et décision Numba

Issue #8, lot 2. Exigences liées : FR-006, SC-003 (D-003), principe VI.

## 1. La question

Au lot 2, on construit les tenseurs d'équité. Pour chaque trio de classes de mains (par exemple AKs / QQ / 76s), ils donnent la part du pot gagnée par chaque joueur à l'abattage : E₃ à trois joueurs, E₂ pour chaque tête-à-tête, la troisième main étant retirée du paquet.

Le plan (§ 3.2) estimait ce calcul à **environ 1 heure**. Ce spike mesure le coût réel avant d'écrire le code (principe VI) et répond à trois questions :

1. Combien de temps prend le calcul du tenseur complet ?
2. Combien coûte l'énumération exhaustive de référence sur 1 000 trios, qui sert à la validation de D-003 (issue #10) ?
3. Faut-il Numba ?

**Budget de temps fixé** : le calcul du tenseur complet peut prendre une nuit (environ 8 h).

## 2. Machine et reproduction

| Élément | Valeur |
|---|---|
| Processeur | Intel Core i5-13420H, 8 cœurs, 12 threads |
| Mémoire | 16 Go |
| Système | Windows 11 |
| Logiciels | Python 3.12.10, NumPy 2.5.5, Numba 0.68.1 (temporaire, hors projet) |

```bash
uv run python benchmarks/spike_equity.py                       # partie NumPy (~1 min 30)
uv run --with numba python benchmarks/spike_equity_numba.py    # partie Numba (~1 min 15)
```

Les deux scripts utilisent la graine `20261126`. Numba n'est **pas** ajouté au projet : `uv run --with numba` l'installe dans un environnement jetable.

## 3. Un peu de théorie

### 3.1 Monte-Carlo : précision et nombre de tirages

On ne peut pas essayer tous les boards pour chacun des 818 805 trios. On **tire au hasard** un trio de combos compatibles, puis un board, et on regarde qui gagne. C'est un sondage.

Chaque tirage donne au joueur une part du pot : 1, 0, 1/2 ou 1/3 selon les partages. L'équité estimée est la moyenne de ces parts. Son erreur typique (l'« écart-type de l'estimation ») vaut :

> **erreur typique = σ / √n**

Ici, σ est l'écart-type d'**un** tirage et n le nombre de tirages. Une part comprise entre 0 et 1 a un σ d'au plus 0,5, soit 50 points.

**Exemple chiffré** : avec σ = 0,44 (la valeur moyenne mesurée) et n = 10 000 tirages, l'erreur typique vaut 0,44 / 100 = 0,0044, soit **0,44 point**. Pour diviser l'erreur par 2, il faut **4 fois plus** de tirages.

### 3.2 Les deux critères de D-003

D-003 impose, sur au moins 1 000 trios comparés à l'énumération exhaustive :

- **Écart moyen < 0,1 point.** L'écart absolu moyen d'une erreur gaussienne vaut σ/√n × √(2/π) ≈ 0,8 × σ/√n. Avec σ = 0,44, il faut n ≈ **121 000** tirages.
- **Écart maximal < 0,3 point.** C'est le critère le plus exigeant. Sur 1 000 trios × 3 joueurs = 3 000 valeurs, la plus mauvaise est loin dans la queue de la distribution, à environ 4,5 erreurs typiques. On exige que les 3 000 erreurs soient toutes sous 0,3 point avec 95 % de confiance, ce qui demande n ≈ **450 000** tirages par trio.

C'est le critère maximal qui fixe le coût.

### 3.3 Pourquoi la stratification par couleurs n'aide pas

Le plan prévoyait un « Monte-Carlo stratifié par motif de couleurs ». L'idée : au lieu de tirer les combos au hasard, on impose la bonne proportion de chaque configuration de couleurs (par exemple « les deux As de AA partagent une couleur avec AKs » ou non). Cela supprime la part de l'erreur qui vient du choix des combos.

La mesure montre que cette part est **négligeable** : la variance totale vaut 1,002 fois la variance à l'intérieur des configurations. Presque toute l'incertitude vient du **board**, pas des couleurs des cartes privées. La stratification ne ferait gagner que 0,2 % de tirages.

### 3.4 Symétries de couleurs (pour l'énumération exacte)

Les quatre couleurs jouent des rôles identiques. A♥K♥ contre Q♠Q♣ a exactement la même équité que A♠K♠ contre Q♥Q♦ : on passe de l'un à l'autre en renommant les couleurs. Deux trios de combos reliés par une des 24 permutations de couleurs forment une même **configuration**, qu'il suffit de calculer une fois, pondérée par le nombre de trios qu'elle représente.

| Trio de classes | Trios de combos compatibles | Configurations |
|---|---|---|
| AA / AKs / KK | 36 | 2 |
| AA / KK / QQ | 216 | 12 |
| AKs / AKo / QQ | 144 | 6 |
| Moyenne sur 3 000 trios tirés | 367 | **16,5** |

L'énumération exacte est ainsi divisée par environ **22** (367 / 16,5).

## 4. Mesures

### 4.1 NumPy (`spike_equity.py`)

| Mesure | Résultat |
|---|---|
| M1 — évaluateur rapide, paquets de 1 000 / 10 000 / 100 000 / 1 000 000 mains | 0,97 / 2,60 / 2,19 / 0,89 M mains/s |
| M2 — Monte-Carlo de bout en bout | **73 800 tirages/s**, dont 52 % pour tirer les boards et 47 % pour évaluer les mains |
| M3 — σ par tirage, E₃ (300 trios × 20 000 tirages) | moyen 0,436, maximal 0,499 |
| M3 — σ par tirage, E₂ | moyen 0,455, maximal 0,499 |
| M3 — tirages nécessaires, écart moyen < 0,1 point | E₃ 121 000, E₂ 132 000 |
| M3 — tirages nécessaires, écart maximal < 0,3 point (95 %) | **E₃ 450 000**, E₂ 464 000 |
| M3 — gain de la stratification par couleurs | ×1,002 (nul) |
| M4 — trios de classes réalisables | 99,97 % (818 532 sur 818 805) |
| M4 — configurations de couleurs par trio | moyenne 16,5, maximum 74 |
| M5 — énumération exacte d'un trio de combos (1 370 754 boards) | 2,12 s |

Remarque sur M1 : le débit de l'évaluateur NumPy dépend de la taille des paquets. Il est maximal vers 10 000 mains, puis baisse sur les gros paquets, qui ne tiennent plus dans le cache du processeur. Le chiffre de 1,32 M mains/s du benchmark de #7 correspond à un paquet de 1 000 000 de mains.

### 4.2 Numba (`spike_equity_numba.py`)

Le prototype Numba reprend la logique et les tables de `evaluate_batch`. Il donne **exactement les mêmes valeurs** que `evaluate_batch` sur 1 000 000 de mains aléatoires, et les mêmes équités que le Monte-Carlo NumPy, aux erreurs de tirage près (AA / AKs / KK : 78,97 / 10,85 / 10,18 % contre 78,95 / 10,88 / 10,17 %).

| Mesure | 1 thread | 12 threads |
|---|---|---|
| N1 — évaluateur (mains/s) | 9,4 M | 88,6 M |
| N2 — Monte-Carlo (tirages/s) | 3,0 M | **23,6 M** |
| N3 — énumération exacte d'un trio de combos | 0,085 s | 0,046 s |

Par rapport à NumPy, le Monte-Carlo est **41 fois** plus rapide sur un thread et **320 fois** plus rapide sur 12 threads. Deux raisons à cela : Numba compile la boucle en code machine, et il réutilise les masques du board pour les trois joueurs au lieu de tout recalculer.

N3 en parallèle passe mal à l'échelle (×1,8 seulement), car la découpe par première carte du board est très déséquilibrée. Pour la référence, il faudra paralléliser **par trio** plutôt qu'à l'intérieur d'un trio.

## 5. Estimations

Hypothèses : 818 532 trios réalisables, 450 000 tirages par trio, 16,5 configurations par trio.

| Calcul | NumPy | Numba, 1 thread | Numba, 12 threads |
|---|---|---|---|
| **Tenseur complet**, Monte-Carlo | ~1 390 h (58 jours) | ~34 h | **~4,3 h** |
| **Référence exacte**, 1 000 trios, avec symétries | ~10 h | ~23 min | quelques minutes (parallélisme par trio) |
| Référence exacte, 1 000 trios, sans symétries | ~216 h | ~8,7 h | — |
| Tenseur complet **exact**, avec symétries | ~8 000 h | ~318 h | ~40 h (estimation, parallélisme par trio sur 8 cœurs) |

**Lecture** :
- Sans Numba, le tenseur complet est **impossible** dans le budget d'une nuit (58 jours). Réduire le nombre de tirages pour tenir 8 h donnerait environ 2 600 tirages par trio, soit une erreur typique d'environ 0,9 point, très loin de D-003.
- Avec Numba et le parallélisme, le tenseur complet tient en **environ 4 à 5 h**. C'est dans le budget, avec une marge d'environ ×2.
- La référence exacte de #10 passe de 10 h à quelques minutes. Cela la rend utilisable confortablement, y compris pendant le développement.
- Un tenseur **entièrement exact**, sans aucune erreur de Monte-Carlo, est envisageable en un week-end (~40 h). Ce n'est pas nécessaire pour D-003, mais c'est une option pour plus tard.
- L'évaluateur de référence naïf (2 800 mains/s) est exclu pour l'énumération de #10 : il lui faudrait environ 280 jours. #10 utilisera l'évaluateur rapide, lui-même validé contre la référence (#7).

## 6. Recommandation

1. **Ajouter Numba** comme dépendance d'exécution du moteur (`numba`, qui entraîne `llvmlite`). Le gain est mesuré : ×41 sur un thread, ×320 avec 12 threads. C'est la seule option mesurée qui fait tenir le tenseur complet dans une nuit. Cette dépendance est à valider (décision D-010) et sera ajoutée dans l'issue qui l'utilise en premier, pas dans ce spike.
2. **Monte-Carlo simple**, uniforme sur les trios de combos compatibles, avec **450 000 tirages par trio**. On abandonne la stratification par couleurs, qui n'apporte rien (§ 3.3).
3. **Énumération de référence (#10)** : avec l'évaluateur rapide en Numba et la réduction par symétries de couleurs (§ 3.4), parallélisée par trio.
4. **Temps de construction attendu** : environ 4 à 5 h sur cette machine, au lieu de l'heure prévue au plan.
5. `evaluate_batch` (NumPy) reste l'évaluateur vectorisé de référence du moteur. Le noyau Numba en sera une seconde implémentation, testée contre lui.

## 7. Points à surveiller

- **Échauffement du processeur** : les mesures durent quelques secondes. Sur 4 à 5 h, un portable peut ralentir. La marge ×2 sur le budget d'une nuit couvre ce risque, à vérifier lors du premier vrai calcul (#12).
- **Reproductibilité (principe III)** : en parallèle, chaque trio devra avoir **sa propre graine**, dérivée de la graine globale et de l'indice du trio. Ainsi, le résultat ne dépendra pas du nombre de threads.
- **D-003 sur le tenseur entier** : D-003 se juge sur un échantillon de ≥ 1 000 trios. Sur l'ensemble des 2,5 millions de valeurs E₃ du tenseur, avec 450 000 tirages, on attend de 10 à 130 valeurs au-delà de 0,3 point d'écart (selon σ, entre 0,44 et 0,50). C'est inévitable avec un Monte-Carlo, et l'écart moyen restera très inférieur à 0,1 point.
- **Débit NumPy selon la taille des paquets** (M1) : si `evaluate_batch` est utilisé sur de gros volumes, il vaudra mieux découper en paquets d'environ 10 000 mains.
