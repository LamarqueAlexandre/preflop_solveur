# Discounted CFR

Note liée à FR-009 et D-014 (issue #19). Code : `engine/solver/cfr.py`.

## 1. Regret et regret matching

Prenons la SB à un nœud, avec une main h. Le **regret** d'une action a mesure ce qu'elle aurait gagné en plus si elle avait toujours joué a à ce nœud, au lieu de sa stratégie σ :

  r(h, a) = v(h, a) − Σ_b σ(b)·v(h, b)

v est la valeur contrefactuelle (voir [valeurs-terminales.md](valeurs-terminales.md)). CFR additionne ces regrets à chaque itération, nœud par nœud et main par main.

Le **regret matching** (Hart & Mas-Colell, 2000) joue chaque action en proportion de son regret cumulé positif :

  σ(a) = R⁺(a) / Σ_b R⁺(b), ou la stratégie uniforme si aucun regret n'est positif

*Exemple* : avec les regrets (fold +3, call −1, all-in +1), on obtient fold 75 %, call 0 % et all-in 25 %.

## 2. La stratégie moyenne

La stratégie courante oscille. C'est la **moyenne des stratégies jouées**, pondérée par le reach du joueur, qui converge.

**À 2 joueurs et somme nulle**, l'écart à l'équilibre décroît en O(1/√T) (Zinkevich et al., 2007).

**À 3 joueurs, il n'y a aucune garantie.** En pratique, CFR donne de bons résultats au poker (Abou Risk & Szafron, 2010), mais c'est l'exploitabilité NashConv (#20, D-001) qui certifie chaque solution.

## 3. Le discount (DCFR, D-014)

Les premières itérations reposent sur des stratégies mauvaises, et il faut oublier leur effet. À la fin de l'itération t :

| Quantité | Facteur | Défaut | Effet |
|---|---|---|---|
| Regrets positifs | t^α / (t^α + 1) | α = 1,5 | oubli léger, qui s'estompe vite |
| Regrets négatifs | t^β / (t^β + 1) | β = 0 → ½ | une action longtemps mauvaise peut revenir vite |
| Somme des stratégies | (t / (t + 1))^γ | γ = 2 | l'itération k pèse ∝ k² dans la moyenne |

Le facteur de la somme des stratégies se compose d'une itération à l'autre. L'itération k reçoit au final le poids Π_{t=k}^{T} (t/(t+1))^γ = (k/(T+1))^γ, soit un poids proportionnel à k^γ.

## 4. Une itération, vectorisée sur les mains

Les joueurs sont mis à jour l'un après l'autre, dans l'ordre BTN, SB, BB. Pour le joueur mis à jour :

1. **Descente** : on calcule le reach de chaque joueur à chaque nœud, pour toutes les classes à la fois. Le reach d'un joueur est multiplié par la probabilité de son action.
2. **Terminaux** : on calcule toutes les valeurs d'un coup (`values_batch`), avec un produit matrice-matrice par tenseur.
3. **Remontée** :
   - à un nœud du joueur, v = Σₐ σₐ·vₐ, les regrets reçoivent vₐ − v et la somme des stratégies reçoit reach × σ ;
   - à un nœud adverse, v = Σₐ vₐ, car la stratégie adverse est déjà dans les reaches des terminaux.
4. **Discount** des regrets et de la somme des stratégies du joueur.

## 5. Le jeu de référence, résolu à la main

C'est un push/fold heads-up entre la SB et la BB, le BTN ayant déjà foldé. Les stacks valent S. Il y a deux classes de mains : « forte » et « faible ». La forte a 75 % contre la faible, et deux classes identiques partagent.

Les gains nets possibles :
- la SB folde : SB −0,5 ;
- la SB pushe et la BB folde : SB +1, BB −1 ;
- la SB pushe et la BB paie : SB 2S·eq − S.

**Équilibre.** Les mains fortes pushent et paient toujours. La SB pushe sa main faible avec une probabilité p, et la BB paie avec sa main faible avec une probabilité q.

- **La BB faible est indifférente** entre payer et folder. Payer vaut −S/2 contre la forte et 0 contre la faible, avec des poids 1 et p. Folder vaut −1. On obtient :

  (−S/2) / (1 + p) = −1, donc **p = S/2 − 1**

- **La SB faible est indifférente** entre pusher et folder. Contre la BB forte (½), elle perd S/2. Contre la BB faible (½), elle gagne +1 si la BB folde et 0 si elle paie. Folder vaut −½. On obtient :

  −S/4 + (1 − q)/2 = −½, donc **q = 2 − S/2**

Le jeu admet donc deux régimes :
- **S = 3** : équilibre mixte, avec p = q = 0,5 ;
- **S = 10** : équilibre pur, la main faible folde des deux côtés.

On vérifie que les mains fortes ne dévient pas. À S = 3, le push de la SB forte vaut +0,625 contre −0,5 pour le fold. Le call de la BB forte vaut +0,5 contre −1 pour le fold.

### Première itération, à la main

Les stratégies sont uniformes au départ. La SB est mise à jour en premier. Pour la main faible, en moyenne sur les mains de la BB :
- push : ½·(½·(−1,5) + ½·1) + ½·(½·0 + ½·1) = +0,125 ;
- fold : −0,5 ;
- nœud : −0,1875 ;
- regrets : push +0,3125, fold −0,3125.

À l'itération suivante, la SB faible pushe donc à 100 %.

Le test `test_first_iteration_regrets` vérifie ces valeurs. Le code les somme sur les deux classes mortes du BTN, ce qui les multiplie par 4. Elles sont ensuite multipliées par ½, le discount de l'itération t = 1.

## 6. Performance

Le détail est dans `benchmarks/README.md`. Une itération à 20bb prend 0,45 s sur le poste de développement.

Le budget de SC-006 donne environ 26 min par solution, soit environ 3 500 itérations à 20bb. Les arbres plus courts sont plus rapides. Le nombre d'itérations nécessaire sera mesuré avec NashConv (#20, #23).

## Références

- M. Zinkevich, M. Johanson, M. Bowling, C. Piccione, *Regret Minimization in Games with Incomplete Information*, NIPS 2007.
- S. Hart, A. Mas-Colell, *A Simple Adaptive Procedure Leading to Correlated Equilibrium*, Econometrica 68(5), 2000.
- N. Brown, T. Sandholm, *Solving Imperfect-Information Games via Discounted Regret Minimization*, AAAI 2019.
- N. Abou Risk, D. Szafron, *Using Counterfactual Regret Minimization to Create Competitive Multiplayer Poker Agents*, AAMAS 2010.
