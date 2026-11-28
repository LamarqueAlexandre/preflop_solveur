# Contenu d'une solution : stratégie, reach et EV par nœud

Note liée à FR-009, FR-011, US2 (scénario 3) et D-015 (issue #23). Code : `engine/solver/node_values.py`, `engine/library/solution.py`.

## 1. Ce qu'on stocke

Pour chaque nœud de décision et chaque classe de main :

- la **stratégie moyenne** du DCFR, c'est-à-dire la fréquence de chaque action. C'est la stratégie qui converge. La stratégie courante du regret matching oscille, on ne la publie pas ;
- l'**EV de chaque action** pour le joueur qui agit ;
- le **reach** de chaque joueur r_p(n, h) : la probabilité que p joue jusqu'au nœud n avec h, en ne comptant que ses propres actions. À la racine, il vaut 1.

Toutes les EV et tous les reaches sont calculés sous cette stratégie moyenne. On stocke aussi l'EV de chaque joueur à chaque nœud, terminaux compris : l'EV d'une action est l'EV de l'acteur au nœud enfant.

## 2. Valeur contrefactuelle et EV conditionnelle

Le solveur manipule des **valeurs contrefactuelles** (Zinkevich et al., 2007, *Regret Minimization in Games with Incomplete Information*) :

  v_i(n, h) = Σ_{x,y} W[h,x,y] · r_j(n,x) · r_k(n,y) · u_i(h, x, y)

C'est une somme sur les mains adverses, pondérée par :
- le nombre de combos compatibles W, qui porte le retrait de cartes ;
- la probabilité que chaque adversaire soit arrivé là avec sa main.

Ce n'est pas une valeur en bb lisible. Pour obtenir « ce que je gagne en moyenne en étant ici avec h », on divise par le poids des mains adverses encore possibles :

  m_i(n, h) = Σ_{x,y} W[h,x,y] · r_j(n,x) · r_k(n,y)
  **EV_i(n, h) = v_i(n, h) / m_i(n, h)**

C'est la règle de Bayes. Les ranges adverses à n sont celles qui ont survécu à leurs propres actions, retrait de cartes compris. L'EV suit la convention D-007 : gain net en bb depuis le début de la main, blinds postées comprises.

**EV non définie.** Si m_i(n, h) = 0, les adversaires n'arrivent jamais à n (par exemple, une ligne que personne ne joue). L'EV n'a alors pas de sens : elle vaut **NaN**, que le front affichera « — ». La valeur 0 a été écartée, car elle ressemblerait à une vraie EV.

## 3. Les relations entre nœuds (testées)

1. **Pour l'acteur.** Son action ne change pas les ranges adverses, donc m(enfant) = m(nœud) :
   EV(nœud, h) = Σₐ σ(a | h) · EV(enfantₐ, h).
   L'EV d'une main à un nœud est la moyenne des EV de ses actions, pondérée par sa stratégie.
2. **Pour un non-acteur p.** L'action de l'acteur modifie la range de l'acteur, donc ce que p peut affronter :
   EV_p(n, h) = Σₐ P(a | h_p) · EV_p(enfantₐ, h),  avec P(a | h_p) = m_p(enfantₐ, h) / m_p(n, h).
   Ici, P(a | h_p) est la probabilité que l'acteur choisisse a, sachant que p tient h. Elle dépend de h à cause du retrait de cartes.
3. **Somme nulle.** À la racine, les EV moyennes des trois joueurs, pondérées par la masse de chaque main, s'additionnent à 0. Elles sont égales aux EV de `Exploitability`.

## 4. Exemple chiffré

On reprend le jeu jouet de [cfr.md](cfr.md) :
- push/fold SB contre BB, le BTN a foldé, stack S = 10 ;
- deux classes, STRONG et WEAK, avec W = 1 (pas de retrait) ;
- STRONG a 75 % d'équité contre WEAK.

À l'équilibre, STRONG pousse et paie, WEAK folde des deux côtés.

**Racine (la SB agit) avec WEAK.**
- Fold : on perd la SB, soit −0,5.
- Push :
  - La BB paie avec STRONG : 0,25 × 20 − 10 = −5.
  - La BB folde avec WEAK : la SB gagne 10 + 1, soit +1.
  - v = (−5) + (+1) = −4 et m = 2 (BTN × BB, une main chacun), donc **EV(push) = −2**.
- La SB folde WEAK : EV(racine, WEAK) = −0,5.

**Nœud « A » (la BB face au push).** Seule STRONG pousse, donc m_BB(A) = 1 : la BB ne fait face qu'à STRONG.
- BB avec WEAK : EV(call) = 0,25 × 20 − 10 = **−5**, EV(fold) = −1.
- BB avec STRONG : EV(call) = 0, EV(fold) = −1.

**BB à la racine (non-acteur).** La SB pousse une fois sur deux, avec STRONG.
- BB avec STRONG : ½ · 0 + ½ · (+0,5) = **+0,25**.
- BB avec WEAK : ½ · (−1) + ½ · (+0,5) = **−0,25**.

En moyenne, les deux joueurs sont à 0, ce qui respecte la somme nulle.

**Si la SB ne pousse jamais**, m_BB(A) = 0 : l'EV de la BB à A est NaN. L'EV de la SB à A reste définie : c'est ce qu'elle gagnerait en poussant.

## 5. Arrêt de la résolution (D-015)

On lance le DCFR par blocs de 100 itérations, puis on mesure NashConv (voir [exploitabilite.md](exploitabilite.md)). On s'arrête dès que NashConv < 0,1 % du pot de départ, ou après 2 000 itérations.

Mesures sur l'arbre complet, avec les vrais tenseurs :

| Profondeur | Nœuds | NashConv après 100 / 200 / 300 itérations |
|---|---|---|
| 10bb | 130 | 0,055 % / 0,012 % / 0,005 % |
| 20bb | 400 | 0,27 % / 0,061 % / 0,026 % |

La cible de 0,1 % laisse une marge de 5× sous le seuil de publication de 0,5 %. Ces chiffres sont **relatifs au modèle** : ils mesurent l'équilibre du jeu avec réalisation d'équité, pas du poker réel.

## 6. Commande

```bash
uv run engine solve --stack 20            # cible 0,1 %, 2 000 itérations au plus
uv run engine solve --stack 8 --profile mon_profil.json --target 0.05
```

La commande affiche la progression, puis le NashConv total et par joueur, l'EV de chaque joueur et les fréquences du BTN à la racine. Elle n'enregistre rien : le stockage arrive avec le `SolutionStore` (#24).
