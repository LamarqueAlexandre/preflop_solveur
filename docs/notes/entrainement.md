# Moteur d'entraînement : tirage des spots, perte d'EV et notation

Note liée à US4, FR-025, D-008, D-009 et D-017 (issue #33). Code : `engine/training/`.

## 1. Un spot

Un spot réunit une solution (une profondeur), un nœud de décision, le joueur qui agit (le **héros**) et sa main. Le joueur voit :
- son stack ;
- sa position ;
- les actions précédentes (`history`) ;
- sa main (`hand`, par exemple `AKo`, et un combo précis, par exemple `AcKh`) ;
- les actions possibles.

Il en choisit une. Le spot contient aussi la clé de correction : la stratégie d'équilibre de cette main et l'EV conditionnelle de chaque action. C'est à l'API de ne pas la montrer avant la réponse.

**Types de spots** (`spot_type`), déduits du niveau de relance et des limps :

| Type | Le héros fait face à… | Exemple (12–20bb) |
|---|---|---|
| `open` | personne n'est entré | `root` (BTN), `F` (SB après un fold du BTN) |
| `vs_limp` | un ou plusieurs limps, sans relance | `C` (SB après un limp du BTN), `F-C` (BB, check option) |
| `vs_raise` | une relance (open ou isolation) | `R2.0`, `A`, `F-C-R3.0` |
| `vs_3bet` | un 3-bet | `R2.5-R7.5` (BB), `R2.5-R7.5-F` (BTN) |
| `vs_4bet` | un 4-bet | `R2.5-R7.5-F-A` (SB) |

## 2. Tirer les spots comme en vrai (D-017)

Pour chaque spot :
1. on tire une **profondeur** uniformément parmi les solutions qui respectent les filtres (positions du héros, plage de stacks, types) ;
2. on tire un **couple (nœud, main)** avec son poids réel :

     poids(n, h) = reach_héros(n, h) × m_héros(n, h)

   La probabilité que le héros arrive en n avec h est multipliée par la masse des mains adverses encore possibles (actions des vilains et retrait de cartes, voir [solution-ev.md](solution-ev.md)). Une main qui n'arrive jamais au nœud a un poids nul, donc on ne la demande jamais ;
3. on tire un **combo** uniformément dans la classe.

Le tout est **reproductible avec une graine**.

**Exemple calculé à la main** (test `test_spots_follow_the_real_frequencies`) : push/fold à 10bb, deux classes, W = 1. La SB pousse STRONG à 100 % et WEAK à 25 %.
- Racine (SB) : poids 4 pour STRONG et 4 pour WEAK. Le reach vaut 1, et la masse adverse vaut 2 × 2 (BTN × BB).
- Nœud « face au push » (BB) : 2,5 pour chacune. La masse vaut 2 × (1 + 0,25), puisque seuls 1,25 « SB » arrivent.
- Le total est de 13. Sur 20 000 tirages, on observe bien 4/13 ≈ 30,8 % pour chaque spot racine et 2,5/13 ≈ 19,2 % pour chaque spot face au push.

**Conséquence.** Les spots fréquents dominent. À 15bb, « la SB après un fold du BTN » (atteint dans ~71 % des mains) sort environ dix fois plus que « la SB face à l'open R2.0 » (~7 %). Beaucoup de spots sont des folds évidents, comme 74o face à un tapis. Un filtre « spots non triviaux » pourra venir plus tard.

## 3. Perte d'EV et notation (D-008, D-017)

  perte(a) = maxₐ' EV(a', h) − EV(a, h)

Ce sont les EV conditionnelles de la solution, en bb.

| Perte | Note |
|---|---|
| < 0,05bb | meilleure action |
| de 0,05 à 0,25bb | imprécision |
| ≥ 0,25bb | erreur |

Les bornes sont testées exactement : 0,0499 donne meilleure action, 0,05 imprécision, 0,2499 imprécision, 0,25 erreur.

**Actions mixtes.** À l'équilibre, les actions d'une stratégie mixte ont **la même EV**. C'est le principe d'indifférence : si l'une valait plus, on ne jouerait que celle-là. Une action jouée **au moins 1 %** du temps est donc notée « meilleure action », même si une petite perte apparaît à cause de la convergence imparfaite.

**Exemple réel** (15bb, la SB avec 88 face à R2.0) : call 51 % (+0,26), all-in 49 % (+0,24), fold 0 % (−0,50).
- **All-in** : perte 0,02bb, fréquence 49 % → meilleure action.
- **Fold** : perte 0,76bb → erreur.

Le seuil de 1 % est nécessaire : la stratégie moyenne du DCFR donne des fréquences de l'ordre de 0,001 à presque tout. Avec « non nulle » au pied de la lettre, presque tout serait juste.

## 4. Bilan de session (US4, scénario 4)

`summarize(answers)` donne :
- le nombre de réponses et la répartition meilleure action / imprécision / erreur ;
- le **score**, c'est-à-dire la part de « meilleure action » ;
- la **perte d'EV totale et moyenne** ;
- la liste des erreurs et imprécisions. Chacune garde son spot (empreinte et nœud), ce qui permettra au front de l'ouvrir dans la vue stratégie.

## 5. Performance (SC-008 : < 300 ms entre deux spots)

Sur la bibliothèque réelle (23 solutions déjà chargées), tirer 20 spots prend **5 à 22 ms**. Charger les 23 solutions depuis le store prend ~0,8 s, une seule fois : c'est à l'API (#34) de les garder en mémoire.
