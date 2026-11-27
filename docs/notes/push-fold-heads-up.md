# Validation push/fold : le sous-cas heads-up (SC-002.1, D-004)

## 1. Le jeu

Le BTN est forcé à folder. Il reste un push/fold heads-up entre la SB et la BB :

- la SB pousse tapis ou folde (pas de limp) ;
- face au tapis, la BB paie ou folde ;
- si la BB paie, on va à l'abattage, à l'**équité exacte** (pas de réalisation).

L'arbre (`build_heads_up_push_fold_tree`) garde les identifiants de l'arbre complet : la SB décide en `F`, la BB en `F-A`, et l'abattage est `F-A-C`. Avec des stacks inégaux, la BB ne met que le stack effectif. L'excédent de la SB forme un pot annexe dont elle est la seule éligible, et il lui revient.

Gains nets de la SB (stacks S, D-007) : fold −0,5 ; push puis fold de la BB +1 ; push puis call : 2S·eq − S.

## 2. Pourquoi la main morte du BTN ne fausse rien

Dans notre moteur, le BTN qui folde garde ses deux cartes, et elles sont retirées du paquet. Les charts heads-up n'ont pas de troisième main. Le moteur résout pourtant exactement le jeu heads-up, pour deux raisons.

**Équité.** Fixons AKo pour la SB et 77 pour la BB. Il reste 48 cartes. Tirer 2 cartes mortes au hasard puis 5 cartes de board parmi les 46 restantes donne au board exactement la même loi qu'un tirage direct de 5 cartes parmi 48. L'équité moyennée sur la main du BTN est donc exactement l'équité heads-up.

**Poids des combos.** Pour une paire de combos SB/BB disjointe, le nombre de mains BTN compatibles vaut toujours C(48, 2) = 1 128. En sommant W sur l'axe du BTN, on retrouve les poids heads-up à cette constante près : le retrait de cartes entre la SB et la BB est conservé, sans biais ajouté.

Le seul écart possible vient donc du bruit Monte-Carlo de E2 (SC-003 : moins de 0,1 point en moyenne).

## 3. La référence

HoldemResources publie l'équilibre de Nash heads-up push/fold chipEV sans ante (https://www.holdemresources.net/hune). La page montre des grilles à seuils : pour chaque main, le stack maximal auquel on pousse ou on paie. Ces grilles arrondissent les mains mixtes en stratégies pures.

On utilise plutôt les **données brutes** de la même page (`holdemresources_hu_equilibrium.zip`, fichiers de 2012). Elles donnent la stratégie non simplifiée, mains mixtes comprises, de 1 à 200bb par pas de 0,05bb. Les lignes 5, 10 et 15bb sont recopiées, avec la source et la date, dans `tests/engine/solver/data/hrc_hu_push_fold_no_ante.csv`.

Chaque profondeur a une seule main mixte de chaque côté. Exemples : à 5bb, la SB pousse 96o 16 % du temps ; à 10bb, la BB paie Q6s 40 % du temps.

Droits : la page porte « © HoldemResources GmbH » et aucune licence ne couvre explicitement la reprise des valeurs. Elles sont reproduites avec attribution, pour la seule validation (choix validé lors de l'issue #21).

## 4. La mesure d'écart

Pour chaque joueur, on mesure l'écart moyen absolu pondéré par les combos :

  écart = Σ_h n_h · |f_solveur(h) − f_chart(h)| / 1 326

Ici n_h est le nombre de combos de la classe h (6, 4 ou 12) et f la fréquence de push (SB) ou de call (BB). C'est la part des 1 326 mains de départ jouées différemment. Contrairement à la comparaison des pourcentages globaux, deux erreurs de sens opposé ne peuvent pas se compenser.

Exemple : si le solveur pousse KTo (12 combos) à 100 % là où la chart folde, l'écart vaut 12 / 1 326 = 0,9 %. Deux mains offsuit entières de travers suffisent presque à dépasser 2 %.

## 5. Résultats (500 itérations de DCFR, tenseurs à 450 000 tirages)

| Stack | Écart push SB | Écart call BB | NashConv (% du pot) |
|---|---|---|---|
| 5bb | 0,003 % | 0,009 % | < 0,0001 % |
| 10bb | 0,005 % | 0,001 % | < 0,0001 % |
| 15bb | 0,006 % | 0,002 % | < 0,0001 % |

Le seuil est de 2 %. L'accord est quasi parfait, mains mixtes comprises : le moteur (tenseurs, valeurs terminales, DCFR) retrouve un équilibre calculé indépendamment.

Le jeu heads-up est à **somme nulle à deux joueurs**. CFR y a une garantie de convergence vers Nash, contrairement au 3-max, et NashConv tombe à environ 0,0006 % du pot dès 100 itérations. Le test ne s'exécute qu'en local : il est marqué `slow` et sauté quand les tenseurs complets sont absents, ce qui est le cas en CI.
