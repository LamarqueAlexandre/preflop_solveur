# Réalisation d'équité et profil par défaut

Note liée à FR-007, FR-008, D-002 et D-012 (issue #17).

## 1. La notion

Le solveur s'arrête au flop. Quand un pot y arrive sans all-in général, il faut décider quelle part du pot revient à chaque joueur. La réponse naïve est « son équité ». Avec 50 % d'équité, le joueur récupérerait 50 % du pot.

En pratique, ce n'est pas le cas. Le joueur **en position** parle après son adversaire à chaque street. Il voit son action avant de choisir la sienne, il prend des cartes gratuites, il bluffe mieux et il paie moins de mises perdantes. Il récupère en moyenne un peu **plus** que son équité. Le joueur **hors de position** en récupère un peu **moins**.

Le **facteur de réalisation** mesure cet écart :

  R = (part du pot gagnée en moyenne) / (équité brute)

Un R de 1,08 signifie que le joueur réalise 108 % de son équité.

## 2. La normalisation (D-002)

Si chaque joueur recevait `Rᵢ·eqᵢ` du pot, la somme des parts ne ferait pas 1 et des jetons apparaîtraient ou disparaîtraient. Le jeu ne serait plus à somme constante, et l'équilibre calculé n'aurait plus de sens. On normalise donc :

  partᵢ = Rᵢ·eqᵢ / Σⱼ Rⱼ·eqⱼ

Deux conséquences :
- seuls les **rapports** entre les facteurs comptent : multiplier tous les R par 2 ne change rien ;
- des facteurs tous égaux (par exemple tous à 1) redonnent exactement l'équité brute.

### Exemple chiffré

Le BTN ouvre à 2bb, la SB folde et la BB paie. Le pot au flop vaut 4,5bb (2 + 2 + 0,5). La tranche est deep, en pot relancé. Le BTN est en position (R = 1,08) et la BB hors de position (R = 0,92). Pour une main donnée, le BTN a 55 % d'équité brute.

| | BTN (IP) | BB (OOP) | Somme |
|---|---|---|---|
| Équité brute | 0,55 | 0,45 | 1 |
| R·eq | 0,594 | 0,414 | 1,008 |
| Part normalisée | 0,589 | 0,411 | 1 |
| Part du pot (bb) | 2,65 | 1,85 | 4,5 |

Le BTN gagne 0,18bb de plus qu'avec son équité brute (2,475bb), et la BB perd exactement autant.

### À 3 joueurs

C'est la même formule avec trois termes. Prenons un pot limpé en deep, avec trois mains à 1/3 d'équité chacune. Les parts deviennent :
- SB (first, 0,87) : 0,87 / 2,94 = 29,6 % ;
- BB (middle, 0,95) : 0,95 / 2,94 = 32,3 % ;
- BTN (last, 1,12) : 1,12 / 2,94 = 38,1 %.

## 3. Pourquoi R se rapproche de 1 quand les stacks raccourcissent

La position a de la valeur parce qu'il reste des décisions à prendre après le flop. La quantité de jeu qui reste se mesure par le **SPR** (*stack-to-pot ratio*), le rapport entre le tapis effectif et le pot au flop :
- avec un SPR proche de 1, une seule mise met tout le monde à tapis. Un pot à tapis se partage à l'équité exacte, donc R ≈ 1 ;
- avec un SPR de 10, il reste trois streets de jeu, et la position pèse beaucoup.

Ordres de grandeur avec les sizings par défaut (D-011) :

| Situation | Pot au flop | Tapis restant | SPR |
|---|---|---|---|
| 6bb, pot limpé SB/BB | 2bb | 5bb | 2,5 |
| 12bb, pot limpé SB/BB | 2bb | 11bb | 5,5 |
| 12bb, BTN ouvre à 2bb, BB paie | 4,5bb | 10bb | 2,2 |
| 20bb, pot limpé SB/BB | 2bb | 19bb | 9,5 |
| 20bb, BTN ouvre à 2bb, BB paie | 4,5bb | 18bb | 4 |
| 20bb, 3-bet à 6bb payé | 12,5bb | 14bb | 1,1 |

Le profil par défaut suit deux règles :
1. **Plus la tranche est courte, plus R est proche de 1** (exigence de FR-008).
2. **À tranche égale, les pots limpés s'écartent le plus de 1, puis les pots relancés, puis les pots 3-betés.** C'est l'ordre des SPR typiques.

À 3 joueurs, l'avantage est encore plus marqué : la SB parle en premier face à deux adversaires, et le BTN parle en dernier. La BB, au milieu, reste proche de 1.

## 4. Les valeurs retenues

Les valeurs sont dans le journal, à la décision D-012, et dans `engine/realization/profiles/default.json`.

Repères pour les justifier :
- À 100bb, les ordres de grandeur habituels sont d'environ 1,0 à 1,15 pour le joueur en position et de 0,7 à 0,9 hors de position. Ces chiffres dépendent fortement de la main et de la range.
- À 25bb ou moins, le SPR est 3 à 10 fois plus petit. On reste donc nettement plus près de 1 : au plus ± 0,13 en deep limpé.
- En short, seuls les pots limpés atteignent le flop avec les sizings par défaut. Les autres valeurs de la tranche (relancé, 3-beté) ne servent qu'à des configurations personnalisées.

**Ces valeurs sont une heuristique, pas une mesure.** Aucune table publiée ne couvre le 3-max Expresso à 25bb ou moins. Le test de sensibilité (#29, SC-009) mesurera l'effet d'une variation de ± 0,1 sur les stratégies. Son rapport décidera si une calibration plus fine est prioritaire pour la V2 (par catégorie de main, voire par agresseur préflop).

## 5. Limites du modèle

- **Un seul facteur par contexte au MVP.** En réalité, une main jouable postflop (connecteurs assortis) réalise mieux qu'une main dominée (as faible dépareillé). C'est le rôle prévu de `hand_category` en V2.
- **Pas de dimension « agresseur préflop ».** Le relanceur préflop réalise mieux son équité que celui qui paie. Ce n'est pas dans FR-007.
- **L'exploitabilité mesurée est relative à ce modèle** (principe II). Un équilibre exact du modèle n'est pas un équilibre du vrai jeu.

## Références

- Will Tipton, *Expert Heads Up No-Limit Hold'em*, vol. 1, D&B Poker, 2012. Modèles préflop simplifiés et réalisation d'équité.
- GTO Wizard, articles de blog sur la réalisation d'équité (« Equity Realization »). Ordres de grandeur qualitatifs selon la position et la profondeur.
