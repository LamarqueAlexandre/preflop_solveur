# Sensibilité de l'équilibre au profil de réalisation (FR-008a, SC-009)

Note liée à FR-007, FR-008, FR-008a, SC-009 et D-002/D-012 (issue #29). Code : `engine/library/sensitivity.py`, commande `engine sensitivity`. Rapport brut : [sensibilite-realisation-rapport.md](sensibilite-realisation-rapport.md).

## 1. La question

Au MVP, le profil de réalisation donne **un facteur R par contexte de flop** : nombre de joueurs, type de pot, tranche et position. C'est le même facteur pour toutes les mains (D-012). La V2 pourrait le moduler par **catégorie de main** : assortie ou non, connecteurs, petites paires, etc. SC-009 demande de décider si c'est prioritaire, en mesurant à quel point la stratégie d'équilibre bouge quand les facteurs varient de ±0,1.

**Rappel (D-002)** : au flop, la part de pot du joueur i vaut R_i·eq_i / Σⱼ R_j·eq_j. Seuls les **rapports** entre facteurs comptent.

## 2. Les variantes

| Variante | Transformation de chaque facteur f | Ce qu'elle teste |
|---|---|---|
| U+ / U− | f ± 0,1 pour tous les facteurs | décalage uniforme, presque neutre par normalisation |
| **E+ / E−** | en position et dernier à parler : f ± 0,1 ; hors de position et premier : f ∓ 0,1 ; milieu : inchangé | **avantage positionnel** accentué ou atténué |

**Exemple** : pot relancé à 2 joueurs, 9–15bb, 50 % d'équité chacun. Le joueur en position reçoit :
- **52,5 %** du pot avec le profil par défaut (1,05 / 0,95) ;
- 52,3 % avec U+ ;
- **57,5 %** avec E+ (1,15 / 0,85) ;
- 50,0 % avec E− (0,95 / 1,05).

## 3. Mesures

À chaque nœud de décision, pour chaque main h :

  d(h) = ½ Σₐ |σ_variante(a, h) − σ_défaut(a, h)|  ∈ [0, 1]

C'est la **part de la stratégie qui change d'action** (distance en variation totale).
- **Écart moyen d'un nœud** : moyenne de d(h), pondérée par la masse de chaque main au nœud, c'est-à-dire le reach de l'acteur × les mains adverses encore possibles. Une main qui n'arrive pas au nœud ne compte pas.
- **Écart maximal** et **mains qui changent d'action majoritaire** : calculés sur les mains qui atteignent le nœud au moins 1 % du temps.
- **Écart moyen global** : moyenne des nœuds, pondérée par leur probabilité d'être atteints.

**Exemple calculé à la main** (test `test_gaps_per_node`) : push/fold à 10bb, deux classes.
- À la racine, WEAK passe de push 25 % à push 75 % : d = ½(0,5 + 0,5) = 0,5. Comme STRONG ne bouge pas, l'écart moyen du nœud vaut 0,25, et WEAK change d'action majoritaire.
- Au nœud de call, WEAK passe de call 0 % à 60 % : d = 0,6, et l'écart moyen vaut 0,3.
- Le nœud de call est atteint avec une probabilité de 0,625, donc l'écart global vaut (1 × 0,25 + 0,625 × 0,3) / 1,625 = **26,9 %**.

## 4. Résultats

Le calcul couvre 5, 12 et 20bb (une profondeur par tranche), avec ±0,1 autour du profil par défaut 1.0.0. Les solutions des variantes sont toutes publiables : NashConv de 0,002 à 0,098 %.

**Écart moyen global** :

| Profondeur | U+ | U− | **E+** | **E−** |
|---|---|---|---|---|
| 5bb | 0,00 % | 0,00 % | 0,01 % | 0,01 % |
| 12bb | 0,44 % | 0,58 % | **10,4 %** | **5,3 %** |
| 20bb | 1,99 % | 2,35 % | **18,5 %** | **17,8 %** |

**Mains qui changent d'action majoritaire** (somme sur tous les nœuds, mains atteignant le nœud ≥ 1 %) :

| Profondeur | U+ | U− | E+ | E− |
|---|---|---|---|---|
| 5bb | 0 | 2 | 26 | 21 |
| 12bb | 42 | 59 | 494 | 477 |
| 20bb | 203 | 219 | 1 001 | 1 150 |

**EV de la SB à la racine** (bb/main), défaut → variante : à 12bb, −0,083 → −0,103 (E+) et −0,066 (E−) ; à 20bb, −0,146 → −0,175 (E+) et −0,088 (E−).

**Nœuds les plus touchés à 20bb (E±)** :
- `F` (la SB après un fold du BTN, atteint 72 % du temps) : écart moyen 29 à 31 % ;
- `root` (ouverture du BTN) : 14 à 18 % ;
- `R2.5-F` (la BB face à l'open à 2,5 du BTN, après un fold de la SB) : 22 à 32 % ;
- `F-C` (la BB après un limp de la SB) : 15 à 20 %.

## 5. Lecture

1. **À ≤ 8bb, le profil ne compte pas.** Le jeu y est presque du push/fold : les pots se règlent à tapis, à l'équité exacte, sans réalisation. Les seuls écarts visibles sont à `F-C` (la BB après un limp de la SB), un nœud atteint dans moins de 0,1 % des mains.
2. **Le décalage uniforme (U±) bouge peu** : 0,4 à 2,4 %. C'est attendu, puisque la normalisation D-002 neutralise un décalage commun. Ce contrôle confirme que la mesure ne réagit pas à un changement qui ne devrait presque rien changer.
3. **L'avantage positionnel (E±) bouge beaucoup dès 9bb** : 5 à 10 % de la stratégie change à 12bb, et ~18 % à 20bb. Ces changements touchent les nœuds les plus fréquents (ouverture du BTN, jeu de blinds), avec des centaines de changements d'action majoritaire. L'EV de la SB varie jusqu'à 0,06bb/main.
4. **Changements de taille ou de ligne ?** Une partie des changements se fait entre tailles de relance. Par exemple, à 20bb en E+, AA, KK, QQ et AKs passent de R2.5 à R2.0 au BTN : la taille change, mais la ligne reste « relancer ». Pour séparer les deux effets, j'ai recalculé l'écart en **regroupant toutes les relances dimensionnées en une seule action** (analyse ponctuelle, hors de la commande).
   - À 20bb : E+ passe de 18,5 % à **15,5 %**, et E− reste à **17,8 %**. U± ne bouge pas (2,0 et 2,3 %).
   - À 12bb, il n'y a qu'une taille d'ouverture (R2.0), donc les chiffres sont inchangés.
   
   **L'essentiel de l'écart vient donc de vrais changements de ligne** (fold, call, limp, relance, tapis), pas des tailles.
5. **Lien avec SC-007.** À 15bb, les paires TT à 44 paient l'open du BTN à l'équilibre au lieu de faire tapis ([sc007.md](sc007.md)). C'est exactement le genre de décision qui dépend de la réalisation après le flop. À 12bb, les variantes E± font changer JJ et TT à `F-C`.

## 6. Recommandation pour la V2 (décision à prendre)

- **À partir de 9bb, la stratégie est sensible aux facteurs de réalisation.** Une erreur de ±0,1 sur l'écart entre position et hors de position déplace 5 à 18 % de la stratégie. Les écarts réels de réalisation **entre catégories de main** sont plausiblement de cet ordre, voire plus, par exemple entre petites paires ou connecteurs assortis et mains dépareillées. Les ignorer biaise donc probablement les ranges de call et de limp.
- **À ≤ 8bb**, la calibration n'a pratiquement pas d'effet.
- **Ma recommandation : faire de la calibration de la réalisation une priorité de la V2** pour les tranches 9–15bb et > 15bb. Il s'agirait d'abord de mieux estimer les facteurs par contexte, puis de les moduler par catégorie de main. La tranche ≤ 8bb n'en a pas besoin. En attendant, l'interface doit continuer d'afficher que les EV et les stratégies sont relatives au profil (FR-018, principe II).
- **La décision t'appartient.** Je n'ai modifié ni le profil par défaut ni `docs/decisions.md`. Si tu retiens cette priorité, elle pourra faire l'objet d'une décision D-017 et d'une entrée dans la feuille de route de la V2.

## 7. Reproduire

```bash
uv run engine sensitivity --output docs/notes/sensibilite-realisation-rapport.md
# ou, si l'exe est bloqué : uv run python -m engine.cli sensitivity ...
```

Les solutions de base viennent de `data/solutions/`. Les variantes vont dans `data/sensitivity/` (16 Mo, hors git). Une relance ne recalcule rien. Le calcul a pris environ 11 min sur l'i5-13420H : 12 variantes, dont 4 à 20bb à 1 min 20 à 2 min 45 chacune.
