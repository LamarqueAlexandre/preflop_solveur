# Ce que l'interface montre d'une solution : résumé, terminal, profondeur

Note liée à US1, US2, FR-021, D-017 et D-018 (issue #30). Code : `engine/library/views.py`, exposé par `api/routes/solutions.py`.

## 1. Le poids d'une main à un nœud

À un nœud de décision, l'interface montre la stratégie du joueur qui parle **sur la range qu'il a à ce moment-là**. Une classe de main h (AA, AKs, 72o…) n'y compte pas pour 1 : elle compte selon la fréquence à laquelle on se retrouve vraiment à ce nœud avec elle.

  w(h) = reach(h) × m(h)

- **reach(h)** : probabilité que le joueur ait joué toutes ses actions précédentes avec h. Si la SB 3-bet AA toujours et AJo une fois sur cinq, au nœud « BTN face au 3-bet », son reach vaut 1 pour AA et 0,2 pour AJo.
- **m(h)** (masse adverse) : `Σ_{x,y} W[h,x,y] · r_j(x) · r_k(y)`. `W` compte les façons de distribuer un combo de chaque classe sans carte commune. m(h) contient donc le nombre de combos de h (6, 4 ou 12) et le **retrait de cartes** : si les adversaires ont des ranges pleines d'as, une main avec un as y arrive moins souvent.

C'est exactement le poids utilisé pour tirer les spots de l'entraînement (D-017). L'entraînement et l'affichage voient donc le même jeu.

## 2. Fréquences globales (FR-021)

  fréquence(a) = Σ_h w(h) · σ(h, a) / Σ_h w(h)

où σ(h, a) est la fréquence de l'action a avec h.

**Exemple du test** (`tests/engine/library/test_views.py`) : deux classes, STRONG et WEAK, de même masse ; `W` vaut 1 partout. À la racine, la SB a reach 1 avec les deux classes, et le BTN (couché) et la BB ont chacun 2 classes « pleines » : m = 2 × 2 = 4 pour chacune. STRONG pousse toujours, WEAK pousse 25 % :

  fold = (4·0 + 4·0,75) / 8 = 0,375  push = 0,625.

Face au push, la BB voit une SB de reach 1 (STRONG) et 0,25 (WEAK) : m = 2 × 1,25 = 2,5 pour chacune de ses classes. Elle paie avec STRONG et folde WEAK : 50 % / 50 %.

## 3. Taille de range

  part(p) = Σ_h masse(h) · reach_p(h) / Σ_h masse(h), et combos = part × 1326.

`masse(h)` est proportionnelle au nombre de combos de h : le nombre de façons de distribuer les deux autres mains, une fois un combo de h donné, ne dépend pas de h. Dans l'exemple, la range de la SB au nœud du push vaut (1 + 0,25) / 2 = 62,5 % des mains.

## 4. Nœud terminal (US2, scénario 4)

Pour chaque joueur, on donne l'EV moyenne (D-007 : gain net depuis le début de la main) sur les mains qui atteignent le terminal, avec le même poids w(h).

**Exemple** : push de la SB payé par la BB, stacks de 10bb, pot de 20bb, équité exacte (pas de réalisation pour un all-in).
- SB : STRONG (poids 2) contre STRONG gagne la moitié du pot, EV = 10 − 10 = 0 ; WEAK (poids 0,5) n'a que 25 % contre STRONG, EV = 5 − 10 = −5. Moyenne : (2·0 + 0,5·(−5)) / 2,5 = **−1bb**.
- BB : +1bb. Le jeu est à somme nulle entre les deux joueurs restants, et le BTN, couché sans mise, a 0.

Un terminal jamais atteint (masse nulle) n'a pas d'EV : la réponse donne `null`.

## 5. Profondeur la plus proche (US1, scénario 4)

On cherche, parmi les solutions **publiables**, celle dont la profondeur (plus petit stack) est la plus proche de la demande. À égalité, la plus basse l'emporte (D-018). Exemple : avec 10, 13, 15 et 20bb en bibliothèque, 14bb renvoie 13bb, 17bb renvoie 15bb et 3bb renvoie 10bb.
