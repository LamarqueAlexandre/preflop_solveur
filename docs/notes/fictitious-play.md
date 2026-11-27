# Validation push/fold 3-max : le *fictitious play* (SC-002.2, D-004)

## 1. Pourquoi une seconde implémentation

Aucune chart de Nash push/fold 3-max chipEV n'est publiée. Pour valider le solveur sur le jeu à trois joueurs, on le compare à un second algorithme, écrit séparément, qui résout le même jeu par un autre mécanisme. Si deux méthodes indépendantes tombent sur les mêmes ranges, une erreur commune est très improbable : il faudrait la même faute dans deux codes différents.

L'indépendance est réelle : `engine/reference/push_fold_fp.py` n'importe que NumPy. Il ne partage avec `engine/solver` que les tenseurs d'équité W, E₃ et E₂. L'arbre, les gains, le calcul des valeurs contrefactuelles et la meilleure réponse sont réécrits à la main.

## 2. L'algorithme

**Intuition.** On rejoue le jeu un très grand nombre de fois. À chaque tour, chaque joueur joue sa **meilleure réponse pure** contre la **moyenne** des stratégies que les autres ont jouées jusque-là. Si les moyennes se stabilisent, personne n'a intérêt à dévier de la moyenne des autres : c'est un équilibre de Nash.

**Formule.** On note σ̄ₜ la stratégie moyenne d'un joueur après t tours, et BRₜ sa meilleure réponse contre σ̄ₜ des autres :

  σ̄ₜ₊₁ = σ̄ₜ + (BRₜ − σ̄ₜ) / (t + 1)

Chaque meilleure réponse pèse 1/(t + 1) : σ̄ₜ est la moyenne arithmétique de toutes les meilleures réponses jouées, avec la stratégie uniforme de départ.

**Exemple chiffré.** Prenons A5o au BTN :
- au tour 1, contre des blinds qui paient large, il folde (BR = 0) ;
- au tour 2, les blinds se sont resserrées, il pousse (BR = 1) ;
- au tour 3, il folde (BR = 0).

Sa fréquence moyenne de push passe de 0 à 0 + (1 − 0)/2 = 0,5, puis à 0,5 + (0 − 0,5)/3 ≈ 0,33. Une main à l'indifférence oscille ainsi entre push et fold, et sa moyenne converge vers sa fréquence d'équilibre mixte.

Les joueurs sont mis à jour **simultanément**, tous contre les moyennes du tour précédent (variante de Robinson). Brown alternait les joueurs ; les deux variantes conviennent.

**Différence avec le DCFR.** Le DCFR accumule des regrets action par action, et sa stratégie courante est proportionnelle aux regrets positifs ([cfr.md](cfr.md)). Le *fictitious play* ne connaît pas de regret : il calcule une meilleure réponse exacte contre une moyenne. Les deux mécanismes sont différents, d'où la valeur de la validation croisée.

**Convergence.** Elle est prouvée en jeu à deux joueurs à somme nulle (Robinson, 1951), pas à trois joueurs, comme pour le DCFR. Le certificat NashConv ([exploitabilite.md](exploitabilite.md)) reste l'arbitre.

## 3. Pourquoi la moyenne nœud par nœud est exacte ici

Dans un arbre général, moyenner des stratégies comportementales nœud par nœud est faux : un nœud qu'une meilleure réponse n'atteint jamais ne doit pas recevoir son poids dans la moyenne. Il faut pondérer chaque nœud par la probabilité que le joueur l'atteigne par ses propres actions (XFP : Heinrich, Lanctot et Silver, 2015, *Fictitious Self-Play in Extensive-Form Games*).

En push/fold, chaque joueur agit **au plus une fois** : le BTN à la racine, la SB après le fold ou le push du BTN, la BB en dernier. Aucun nœud d'un joueur ne suit un autre de ses nœuds, donc cette probabilité vaut toujours 1 et la moyenne simple est exacte.

## 4. Le jeu

| Nœud | Joueur | Actions |
|---|---|---|
| `root` | BTN | fold, push |
| `F` | SB | fold, push |
| `F-A` | BB | fold, call |
| `A` | SB | fold, call |
| `A-F` | BB | fold, call |
| `A-C` | BB | fold, call |

Gains nets avec des stacks S (D-007), « éq » étant l'équité exacte de la main dans le pot :

| Terminal | BTN | SB | BB |
|---|---|---|---|
| `F-F` | 0 | −0,5 | +0,5 |
| `F-A-F` | 0 | +1 | −1 |
| `F-A-C` | 0 | 2S·éq − S | 2S·éq − S |
| `A-F-F` | +1,5 | −0,5 | −1 |
| `A-F-C` | (2S + 0,5)·éq − S | −0,5 | (2S + 0,5)·éq − S |
| `A-C-F` | (2S + 1)·éq − S | (2S + 1)·éq − S | −1 |
| `A-C-C` | 3S·éq − S | 3S·éq − S | 3S·éq − S |

À deux joueurs, l'équité est lue dans E₂ (la main du troisième est morte, retirée du paquet) ; à trois, dans E₃. W porte le retrait de cartes : un triplet impossible a un poids nul.

Valeur contrefactuelle de la main h du joueur i au terminal z, avec j < k ses adversaires et r leur probabilité d'atteindre z :

  v_iz(h) = Σ_{x, y} W[h, x, y] · r_jz(x) · r_kz(y) · u_iz(h, x, y)

La meilleure réponse de i en un nœud compare, main par main, la somme des v_iz des terminaux sous « fold » et sous « push/call ». Une égalité exacte (nœud jamais atteint par les adversaires) donne 0,5, comme la stratégie uniforme du DCFR quand ses regrets sont nuls.

**Coût.** Les quatre tenseurs de gains (W, W·E₃, W·E₂ et sa transposée) sont indexés par classes, pas par sièges : ils sont les mêmes pour les trois joueurs. Une itération fait donc un seul produit matriciel par tenseur, contre les 21 produits de reach (3 joueurs × 7 terminaux) empilés. Environ 50 ms par itération sur les 169 classes (2 000 itérations : 1 min 30 par profondeur).

## 5. Résultats

DCFR : 500 itérations. *Fictitious play* : 2 000 itérations. Écart = Σ_h n_h · |f_DCFR(h) − f_FP(h)| / 1 326, à chaque nœud.

| Stack | NashConv DCFR | NashConv FP | Écart max (nœud) |
|---|---|---|---|
| 5bb | 0,0000 % | 0,058 % | 0,31 % (`A-F`) |
| 10bb | 0,0001 % | 0,104 % | 0,42 % (`F`) |
| 15bb | 0,0001 % | 0,156 % | 0,66 % (`root`) |

Le seuil de SC-002.2 est de 2 % : la marge est large. Le NashConv du *fictitious play* décroît en 1/t (0,83 % à 250 itérations, 0,41 % à 500, 0,21 % à 1 000, 0,10 % à 2 000 à 10bb). Les écarts résiduels viennent surtout de lui : le DCFR est à un NashConv mille fois plus petit.

## 6. Références

- G. W. Brown (1951), *Iterative solution of games by fictitious play*, in *Activity Analysis of Production and Allocation*.
- J. Robinson (1951), *An iterative method of solving a game*, Annals of Mathematics 54(2).
- J. Heinrich, M. Lanctot, D. Silver (2015), *Fictitious Self-Play in Extensive-Form Games*, ICML.
