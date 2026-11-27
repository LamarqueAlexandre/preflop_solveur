# Valeurs terminales

Note liée à FR-007, D-002, D-007, D-013 (issue #18). Code : `engine/solver/terminal.py`.

## 1. Ce que CFR demande à un terminal

À chaque terminal, CFR a besoin de la **valeur contrefactuelle** de chaque main du joueur i : son gain moyen avec cette main, pondéré par la probabilité que les adversaires soient arrivés là avec chacune de leurs mains.

  vᵢ(h) = Σₓ,ᵧ W[h,x,y] · rⱼ(x) · rₖ(y) · uᵢ(h,x,y)

- **W[h,x,y]** est le nombre de triplets de combos sans carte commune. C'est le **retrait de cartes** : avec AA, il ne reste qu'un combo d'AA aux adversaires.
- **rⱼ(x)** est le *reach* de l'adversaire j avec la classe x, par combo : la probabilité qu'il ait joué la suite d'actions qui mène au nœud. Un joueur qui a foldé a toujours un reach, car ses cartes restent retirées du paquet.
- **uᵢ** est le gain net de i depuis le début de la main, blinds comprises (D-007).

Ces valeurs ne sont **pas normalisées** : c'est la convention de CFR (Zinkevich et al., 2007, *Regret Minimization in Games with Incomplete Information*). Pour obtenir une EV en bb, on divise par la masse Σ W·r·r·r (`expected_values`).

## 2. Les trois types de terminal

| Type | Gain uᵢ | Tenseur contracté |
|---|---|---|
| Fold | pot − cᵢ pour le gagnant, −cᵢ sinon | W |
| Showdown (all-in) | Σ des pots : E₃ à 3, E₂ à 2 (troisième main morte), le pot entier s'il n'y a qu'un éligible ; − cᵢ | W·E₃, W·E₂ |
| Flop | pot · Rᵢeqᵢ / Σⱼ Rⱼeqⱼ − cᵢ | W·S (parts réalisées) |

**Pots annexes.** L'espérance est linéaire : on additionne les pots.

*Exemple* : stacks 5/10/10. Le BTN est à tapis pour 5bb, la SB à tapis pour 10bb, la BB paie. Le pot principal fait 15bb, disputé à 3. Le pot annexe fait 10bb, disputé entre la SB et la BB, avec la main du BTN morte.

  EV_SB = 15·E₃(SB) + 10·E₂(SB vs BB | BTN mort) − 10

Si la SB a 60 % à 3 et 75 % contre la BB, son EV vaut 9 + 7,5 − 10 = +6,5bb.

**Flop.** La part réalisée n'est **pas linéaire** en l'équité, à cause de la division. Il faut donc calculer, triplet de mains par triplet de mains, un tenseur de parts S, puis le contracter. Ces tenseurs sont mis en cache par contexte (joueurs vivants, type de pot).

*Exemple* : le BTN ouvre à 2bb, la SB folde, la BB paie. Le pot vaut 4,5bb. Avec R = 1,2 en position et 0,8 hors de position, et une équité de 75 % pour le BTN, sa part vaut 0,9 / (0,9 + 0,2) = 9/11 du pot.

**Jamais de réalisation sur un all-in** (principe II). Un test compare un profil plat et un profil extrême : les valeurs aux folds et aux showdowns sont identiques, seules celles du flop changent.

## 3. Somme constante

À chaque terminal, les parts de pot de chaque triplet somment à 1, donc Σᵢ EVᵢ = 0.

Les tenseurs stockés sont en float32. La somme des parts y dévie de 1 d'au plus 4,5·10⁻⁸. Au chargement, `EquityTables` passe en float64 et **renormalise chaque triplet**. Le jeu devient exactement à somme constante, ce qui compte pour l'exploitabilité NashConv (D-001). Les triplets impossibles (W = 0), stockés en NaN, sont remis à 0.

## 4. Performance

La contraction est le chemin critique : 169³ ≈ 4,8 M produits par appel. Elle s'écrit comme un produit matrice-vecteur sur le tenseur aplati, à condition que le tenseur soit contigu en mémoire. On n'aplatit pas le tenseur en changeant l'ordre de ses axes, car ce changement forcerait une copie. On note plutôt **quel siège possède chaque axe**, et on choisit l'ordre des produits selon la position du joueur.

Mesures (`benchmarks/README.md`) :
- de 1,7 à 6 ms par appel, contre 12,8 ms avec `einsum` ;
- 3,6 s pour une passe complète de l'arbre 20bb.

**Point d'attention pour #19.** Le budget de SC-006 est de 10 h pour 23 solutions, soit environ 26 min par solution. Une itération de CFR sur l'arbre 20bb coûterait environ 3,6 s, ce qui ne laisse qu'environ 430 itérations. Il faudra mutualiser les contractions entre joueurs et entre nœuds dans CFR.
