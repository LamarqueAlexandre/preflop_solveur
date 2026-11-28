# Meilleure réponse contre des vilains verrouillés

Note liée à FR-014 à FR-016, FR-018, D-006 et SC-005 (issue #27). Code : `engine/best_response/`.

## 1. Le principe

On part d'une solution d'équilibre stockée et on **verrouille** la stratégie d'un ou des deux vilains à un ou plusieurs nœuds :

```python
locks = {"root": stratégie (actions × 169)}   # par exemple « le BTN ouvre 100 % »
```

- **Aux nœuds verrouillés**, le vilain joue la stratégie fixée.
- **Ailleurs**, les vilains gardent leur stratégie d'équilibre (FR-015). En particulier, le troisième joueur, s'il n'est pas verrouillé, reste à l'équilibre.
- **Le héros** ne peut pas être verrouillé.

La **meilleure réponse** du héros est la stratégie qui maximise son EV contre ces stratégies figées.

## 2. Une seule remontée de l'arbre

Préflop, toutes les actions sont publiques. Une décision du héros, c'est donc un couple (nœud, main), et la meilleure réponse se calcule en **une remontée**, sans itérer (voir [exploitabilite.md](exploitabilite.md)) :

- **aux terminaux** : les valeurs contrefactuelles du héros, avec les ranges des vilains sous leurs stratégies verrouillées ou d'équilibre ;
- **aux nœuds du héros** : v(h) = maxₐ vₐ(h) ;
- **aux nœuds des vilains** : v = Σₐ vₐ, puisque leur stratégie est déjà dans les reaches.

La même remontée, avec Σₐ σₐ·vₐ au lieu du max, donne la valeur de la **stratégie d'équilibre du héros** contre les mêmes vilains. Le code partage cette remontée avec NashConv (`engine.solver.response_values`).

## 3. EV gagnée (D-006)

  EV gagnée = EV(meilleure réponse contre les vilains verrouillés) − EV(**équilibre** du héros contre ces **mêmes** vilains)

On isole ainsi ce que rapporte **l'adaptation du héros**. Si l'on comparait à l'EV d'équilibre contre des vilains à l'équilibre, on mélangerait deux effets : l'erreur du vilain et l'adaptation du héros.

Elle est donnée à trois niveaux :
- **au total**, en bb par main distribuée ;
- **par main distribuée** au héros (169 valeurs) ;
- **à chaque nœud du héros**, par main, en EV conditionnelle : « je suis ici avec h, combien je gagne en m'adaptant à partir d'ici ». C'est la même normalisation que les EV de la solution ([solution-ev.md](solution-ev.md)). Elle vaut NaN si les vilains n'arrivent jamais à ce nœud.

**Sans verrouillage**, l'EV gagnée est exactement le terme du héros dans NashConv. Sur la bibliothèque, ça donne 0,0004 à 0,0006bb/main, c'est-à-dire ≈ 0.

## 4. Exemple calculé à la main

On reprend le jeu jouet de [cfr.md](cfr.md) :
- push/fold SB contre BB, stack S = 3, le BTN a foldé ;
- STRONG a 75 % d'équité contre WEAK, W = 1.

À l'équilibre, STRONG pousse et paie, et WEAK pousse et paie une fois sur deux.

**On verrouille la SB à « push 100 % » et la BB est le héros.**
- BB avec WEAK, call : contre STRONG 0,25 × 6 − 3 = −1,5, contre WEAK 0, soit −0,75 en moyenne. Fold : −1.
- La meilleure réponse paie à 100 % (−0,75). L'équilibre, qui mélange 50/50, rapporte ½(−0,75) + ½(−1) = −0,875.
- **EV gagnée par WEAK : +0,125bb.** L'écart de fréquence est de +50 points sur le call.
- STRONG paie déjà à 100 % : gain 0.
- **Total : (0 + 0,125)/2 = +0,0625bb/main.**

En poker : la SB pousse trop large, donc la BB doit payer plus large que l'équilibre.

**On verrouille la BB à « call 100 % » (calling station) et la SB est le héros.**
- SB avec WEAK, push : −0,75. Fold : −0,5.
- La meilleure réponse folde. L'équilibre, qui pousse une fois sur deux, rapporte −0,625.
- **Gain +0,125** pour WEAK, et +0,0625bb/main au total.

Contre quelqu'un qui paie tout, on arrête de bluffer.

## 5. Égalités : on garde l'équilibre

Quand, pour une main, le mélange d'équilibre est **déjà optimal** (à 1e-9bb près, en EV conditionnelle), la meilleure réponse le garde au lieu de choisir une action pure arbitraire. C'est toujours une meilleure réponse, puisque tout mélange d'actions optimales en est une.

Sans cette règle, on afficherait des écarts de fréquence parasites. Par exemple, à un nœud que les vilains n'atteignent jamais, toutes les actions valent 0 et l'on afficherait « fold 100 % ». Avec la règle, un verrouillage qui ne change rien n'affiche aucun écart.

## 6. Limites du calcul (FR-018)

Chaque résultat porte ces trois avertissements, affichés tels quels par l'interface :
1. **Les vilains ne s'adaptent pas.** Aux nœuds non fixés, ils gardent l'équilibre, et le troisième joueur reste à l'équilibre.
2. **La stratégie est maximalement exploitante.** Elle est pure là où elle s'écarte de l'équilibre et exploite au maximum la stratégie fixée. Elle serait elle-même très exploitable si le vilain s'adaptait.
3. **Les EV dépendent du modèle**, en particulier du profil de réalisation d'équité. Ce ne sont pas celles du poker réel.

## 7. Performance (SC-005 : < 5 s, objectif < 1 s)

Mesures sur la bibliothèque réelle (`benchmarks/bench_best_response.py`, héros SB, i5-13420H) :

| Profondeur | À froid | À chaud |
|---|---|---|
| 5bb | 0,4 à 0,5 s | 0,04 s |
| 12bb | 1,1 s | 0,13 s |
| 20 et 25bb | 1,8 à 1,9 s | 0,26 à 0,28 s |

- **À froid**, le temps inclut la construction des valeurs terminales de la solution, dont le cache des parts au flop.
- **À chaud**, l'appelant les réutilise, d'où `exploit_solution(solution, terminal_values, locks, hero)`. C'est à l'API (#31) de garder ces valeurs en mémoire par solution.

Exemple de gain : à 20bb, si le BTN relance à 2,5bb avec 100 % de ses mains, la meilleure réponse de la SB gagne **+1,33bb/main** par rapport à son équilibre. Le test de référence SC-007 (le BTN ouvre 100 % à 15bb) fait l'objet de l'issue #28.
