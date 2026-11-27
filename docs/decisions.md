# Journal de décisions

Ce journal consigne les décisions qui touchent le modèle de jeu, la validation ou l'organisation du projet (constitution, « Workflow de développement »). Une décision n'est jamais modifiée après coup : on en ajoute une nouvelle qui la **remplace**, et on met à jour le statut de l'ancienne.

**Format** : contexte → décision → alternatives écartées → conséquences.

**Statuts** : *Proposée* (en attente de validation dans une PR), *Acceptée*, *Remplacée par D-xxx*, *Abandonnée*.

> **Note** : les alternatives écartées de D-001 à D-008 ont été reconstituées a posteriori lors de la rédaction de ce journal (le plan ne les listait pas). Elles sont à relire.

---

## D-001 — Mesure d'exploitabilité : NashConv

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-010, SC-001, SC-002.3

**Contexte.** FR-010 demande une exploitabilité « en pourcentage du pot de départ » et un seuil de publication, sans préciser la mesure. À 3 joueurs, CFR n'a aucune garantie théorique de convergence vers un équilibre de Nash : la mesure d'exploitabilité est donc le seul certificat d'équilibre.

**Décision.** L'exploitabilité est le **NashConv** : la somme, sur les trois joueurs, de `EV(meilleure réponse) − EV(stratégie actuelle)`. Elle est exprimée en % du pot de départ (1,5bb). Une solution est publiable si NashConv < 0,5 %.

**Alternatives écartées.**
- *Exploitabilité moyenne par joueur (NashConv / 3)* : plus flatteuse d'un facteur 3 pour le même seuil, et moins standard dans la littérature.
- *Gain maximal d'un seul joueur* : ignore les écarts des deux autres joueurs.

**Conséquences.** Le calcul de meilleure réponse (#20) sert à la fois à l'exploitabilité et, avec verrouillages, à l'exploitation (#27). Toute exploitabilité affichée reste relative au modèle (principe II).

---

## D-002 — Normalisation de la réalisation d'équité

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-007, FR-008

**Contexte.** Appliquer un facteur de réalisation Rᵢ à l'équité de chaque joueur ne redistribue pas exactement le pot : la somme des Rᵢ·eqᵢ diffère en général de 1. Le jeu cesse alors d'être à somme constante, ce qui fausse l'équilibre.

**Décision.** Au flop, la part de pot du joueur i vaut `Rᵢ·eqᵢ / Σⱼ Rⱼ·eqⱼ`. Le pot est toujours entièrement redistribué.

**Alternatives écartées.**
- *Part brute Rᵢ·eqᵢ, sans normalisation* : crée ou détruit des jetons ; le jeu n'est plus à somme constante.
- *Normalisation additive (répartir l'écart à parts égales)* : peut produire des parts négatives pour les mains faibles.

**Conséquences.** Les facteurs n'ont de sens que relativement les uns aux autres. La somme des EV des joueurs est nulle à chaque terminal (critère de test de #18).

---

## D-003 — Précision des équités (révision de SC-003)

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-006, SC-003

**Contexte.** La formulation initiale de SC-003 (« moins de 0,1 point ») ne précisait pas s'il s'agissait d'un écart moyen ou maximal. Un écart maximal de 0,1 point sur toutes les confrontations imposerait un nombre de tirages Monte-Carlo très élevé.

**Décision.** Sur au moins 1 000 triplets de classes comparés à l'énumération exhaustive : écart **moyen** < 0,1 point et écart **maximal** < 0,3 point.

**Alternatives écartées.**
- *Écart maximal < 0,1 point* : coût de calcul disproportionné pour un gain négligeable sur les stratégies.
- *Énumération exhaustive complète des tenseurs* : coût prohibitif (à confirmer par le spike, #8).

**Conséquences.** SC-003 est réécrit dans la spec. Le nombre de tirages est calibré par le spike (#8).

---

## D-004 — Validation push/fold sans chart 3-max (révision de SC-002)

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : SC-002, constitution principe V

**Contexte.** La version initiale de SC-002 et la constitution (1.0.0, principe V) prévoyaient une comparaison à des charts de Nash push/fold 3-max chipEV publiées. Aucune chart de ce type n'est disponible.

**Décision.** La solution push/fold est validée de trois façons :
1. **Sous-cas heads-up** : le BTN est forcé à folder ; les ranges SB et BB sont comparées aux charts de Nash push/fold heads-up chipEV publiées, sur au moins trois profondeurs, avec moins de 2 % d'écart en fréquence.
2. **Implémentation indépendante** : un *fictitious play* écrit séparément sur l'arbre push/fold 3-max ; moins de 2 % d'écart en fréquence de push avec le solveur principal, sur au moins trois profondeurs.
3. **Certificat d'équilibre** : NashConv < 0,5 % du pot de départ.

**Alternatives écartées.**
- *Charts 3-max ICM* : modèle différent (ICM et non chipEV), comparaison non pertinente.
- *Certificat NashConv seul* : vérifie la cohérence interne du solveur, mais pas l'exactitude du modèle de jeu (règles, équités).

**Conséquences.** Constitution amendée en 1.0.1 (principe V). Issues #21 et #22.

---

## D-005 — Règles d'arbre complémentaires à FR-004

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-004, FR-005

**Contexte.** FR-004 et FR-005 laissent trois situations non définies : la réponse à une relance d'isolation, la possibilité pour un limper relancé de sur-relancer, et la profondeur maximale des relances.

**Décision.**
- Face à une relance d'isolation, le joueur dispose du jeu d'actions « face à une relance » de sa tranche.
- Un limper relancé peut sur-relancer.
- Au plus un 4-bet, toujours all-in.

**Alternatives écartées.**
- *Limper relancé limité à fold / call* : interdirait le limp-reraise, une ligne réelle en Expresso.
- *5-bet autorisé* : à 25bb maximum, un 4-bet non all-in laisse trop peu derrière pour qu'un 5-bet soit autre chose qu'un all-in ; agrandit l'arbre sans valeur.

**Conséquences.** Issues #15 et #16.

---

## D-006 — EV gagnée par la meilleure réponse

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-016, SC-007

**Contexte.** FR-016 demande « l'EV gagnée » par la meilleure réponse sans dire par rapport à quoi.

**Décision.** EV gagnée = EV(meilleure réponse contre les vilains verrouillés) − EV(stratégie d'équilibre du héros contre ces **mêmes** vilains verrouillés). Calculée main par main et au total, en bb/main.

**Alternatives écartées.**
- *Comparer à l'EV d'équilibre contre des vilains à l'équilibre* : mélange deux effets, l'erreur du vilain et l'adaptation du héros. La mesure retenue isole le gain dû à l'adaptation.

**Conséquences.** Sans verrouillage, l'EV gagnée est nulle sur une solution convergée (critère de test de #27).

---

## D-007 — Convention d'EV

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-011

**Contexte.** Une EV peut se mesurer depuis le début de la main ou depuis le nœud courant, en comptant ou non les blinds postées.

**Décision.** EV = gain net en bb depuis le début de la main, les blinds postées comptant comme investies.

**Alternatives écartées.**
- *EV depuis le nœud courant* : rend les EV de nœuds différents non comparables.
- *Blinds non comptées* : fold en SB afficherait 0 au lieu de −0,5bb, ce qui masque le coût réel.

**Conséquences.** Fold en SB = −0,5bb ; fold en BB après un open = −1bb. La somme des EV des trois joueurs est nulle.

---

## D-008 — Notation de l'entraînement

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : US4, FR-025

**Contexte.** US4 demande une note « meilleure action / imprécision / erreur » sans seuils.

**Décision.** Meilleure action si perte < 0,05bb ; imprécision de 0,05 à 0,25bb ; erreur si perte ≥ 0,25bb. Seuils paramétrables. Une action à fréquence d'équilibre non nulle compte comme correcte.

**Alternatives écartées.**
- *Seuils relatifs (en % du pot)* : moins lisibles pour l'utilisateur, qui raisonne en bb.

**Conséquences.** Issue #33.

---

## D-009 — Placement de la logique d'entraînement au lot 8

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : US4, constitution principe IV

**Contexte.** Le plan (§ 3.8) place le tirage des spots, la perte d'EV et la notation dans `engine/training`, mais aucun lot du § 7 ne contenait ce travail.

**Décision.** `engine/training` est développé au lot 8, juste avant la route `/training/sessions` qui l'expose.

**Alternatives écartées.**
- *Lot 7* : regroupé avec la meilleure réponse, sans lien fonctionnel.
- *Dans l'API* : interdit par le principe IV (logique de poker).

**Conséquences.** Issue #33, avant #34. Plan § 7 mis à jour.

---

## D-010 — Calcul des tenseurs d'équité : Numba et Monte-Carlo simple

- **Date** : 2026-11-26 · **Statut** : Acceptée · **Liens** : FR-006, SC-003, D-003, constitution principe VI

**Contexte.** Le plan (§ 3.2) prévoyait un Monte-Carlo stratifié par motif de couleurs, d'environ 1 h de calcul, et Numba « seulement si le spike le justifie ». Le spike #8 ([notes/spike-equites.md](notes/spike-equites.md)) a mesuré :
- **Nombre de tirages** : pour respecter D-003, il faut environ **450 000 tirages par trio**. C'est le critère d'écart maximal < 0,3 point sur 3 000 valeurs qui l'impose.
- **Temps de calcul** : en NumPy, environ **1 390 h** pour les 818 532 trios réalisables. Avec un prototype Numba sur 12 threads, environ **4,3 h**, soit 320 fois plus rapide.
- **Stratification par couleurs** : aucun gain (variance ×1,002). L'incertitude vient presque entièrement du board.
- **Référence exhaustive (#10)** sur 1 000 trios, avec réduction par symétries de couleurs : environ 10 h en NumPy, environ 23 min avec Numba sur un seul thread.

Le budget accepté pour la construction du tenseur est **une nuit** (environ 8 h).

**Décision.**
1. `numba` devient une dépendance d'exécution du moteur. Elle est ajoutée dès l'issue #8, à la demande du propriétaire du projet, et sera utilisée pour la première fois dans l'issue #10.
2. E₃ et E₂ sont calculés par un Monte-Carlo **simple** : trio de combos compatibles tiré uniformément, puis board tiré uniformément. On fait 450 000 tirages par trio, dans une seule passe qui donne E₃ et E₂ en même temps. Le calcul est parallélisé par trio, chaque trio ayant sa propre graine dérivée de la graine globale (principe III).
3. L'énumération de référence (#10) utilise l'évaluateur rapide (noyau Numba) et la réduction par symétries de couleurs.
4. Le noyau Numba est une seconde implémentation de `evaluate_batch`, testée contre lui. `evaluate_batch` reste dans le moteur.

**Alternatives écartées.**
- *Pur NumPy* : 58 jours de calcul, ou une erreur d'environ 0,9 point si l'on se limite à une nuit. Incompatible avec D-003.
- *Monte-Carlo stratifié par couleurs* : gain mesuré nul, pour une complexité supplémentaire.
- *Tenseur entièrement exact (énumération)* : environ 40 h estimées avec Numba. Hors du budget d'une nuit, et inutile pour D-003. Option à rouvrir plus tard si besoin.
- *Table de type Two Plus Two (130 Mo)* : non mesurée. Numba suffit à tenir le budget, sans fichier de données supplémentaire.

**Conséquences.** Le temps de construction attendu passe d'environ 1 h à **4 à 5 h** sur la machine de développement. Le plan § 3.2 et § 8 est mis à jour. Les issues #10, #11 et #12 suivent cette méthode.

---

## D-011 — Interprétation des sizings de FR-004

- **Date** : 2026-11-27 · **Statut** : Acceptée · **Liens** : FR-004, FR-005, cas limite « relance qui engage la quasi-totalité du stack »

**Contexte.** FR-004 décrit les sizings par tranche (« 2x », « 3-bet à 3x la relance », « 3bb + 1bb par limper supplémentaire », « < 1bb derrière ») sans préciser leur base de calcul.

**Décision.**
1. **« 2x », « 2,5x »** : relance **à** 2bb et 2,5bb au total (montant total engagé par le relanceur, BB comprise).
2. **« 3-bet à 3x la relance »** : 3-bet à 3 fois le montant total de la relance. Une ouverture à 2,5bb donne un 3-bet à 7,5bb.
3. **Relance d'isolation « 3bb + 1bb par limper supplémentaire »** : 3bb au total face à un limper, 4bb face à deux. La complète de la SB compte comme un limp.
4. **Conversion en all-in** : une relance est remplacée par un all-in si le stack restant après la relance est **strictement** inférieur à 1bb. Avec exactement 1bb derrière, la relance est conservée.

**Alternatives écartées.**
- *« 2x » = relance de 2bb en plus de la BB (soit 3bb au total)* : contraire à l'usage courant (« min-raise »).
- *« 3x la relance » = 3 fois l'incrément de la relance* : moins usuel, et donne des 3-bets plus petits que ceux observés en Expresso.
- *Complète de la SB non comptée comme limp* : la SB qui complète met le même montant qu'un limper et reste dans le pot ; la relance d'isolation doit en tenir compte.
- *Seuil inclusif (≤ 1bb)* : arbitraire ; le seuil strict garde la relance quand elle laisse exactement 1bb.

**Conséquences.** Issue #13 (`GameConfig`, table de sizings), puis #15 et #16 (construction de l'arbre).

---

## D-012 — Format et profil de réalisation par défaut

- **Date** : 2026-11-27 · **Statut** : Acceptée · **Liens** : FR-007, FR-008, D-002, D-005, issue #17

**Contexte.** FR-008 exige un profil de réalisation par défaut, documenté, avec des facteurs qui se rapprochent de 1 quand la tranche raccourcit. Aucune table publiée ne couvre le 3-max à 25bb ou moins. Il faut aussi fixer le format du profil et le sens des dimensions de FR-007.

**Décision.**
1. **Format** : fichier JSON (`format_version` 1) avec `name`, `version`, `description` et une liste d'entrées `(players, pot_type, tranche, position, factor)`. Le profil par défaut est livré avec le moteur (`engine/realization/profiles/default.json`).
2. **Grille complète** : un profil couvre les 45 contextes (18 à 2 joueurs, 27 à 3 joueurs), y compris ceux que les sizings par défaut ne rendent pas atteignables (par exemple un pot relancé au flop en tranche short). Les sizings étant configurables (FR-004), ce qui est atteignable dépend de la configuration.
3. **Sens des dimensions** :
   - type de pot : niveau de relance 0 → limpé, 1 → relancé (isolation comprise), 2 → 3-beté ;
   - le niveau 3 (4-bet, toujours all-in, D-005) n'a pas de type de pot : aucun pot 4-beté n'atteint le flop avec des stacks égaux. Le cas des stacks inégaux est reporté à la V2 ;
   - position au flop : ordre de parole SB, BB, BTN ; à 2 joueurs `oop`/`ip`, à 3 joueurs `first`/`middle`/`last`.
4. **`hand_category` (V2)** : clé optionnelle d'une entrée, qui précise l'entrée de base du même contexte. Elle est chargée et validée, mais ignorée au MVP (un facteur par contexte).
5. **Valeurs par défaut** (version 1.0.0), heuristiques, justifiées dans [notes/realisation-equite.md](notes/realisation-equite.md) :

|  | 2j IP | 2j OOP | 3j first (SB) | 3j middle (BB) | 3j last (BTN) |
|---|---|---|---|---|---|
| short limpé | 1,03 | 0,97 | 0,96 | 0,99 | 1,04 |
| short relancé | 1,02 | 0,98 | 0,97 | 0,99 | 1,03 |
| short 3-beté | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| medium limpé | 1,07 | 0,93 | 0,91 | 0,97 | 1,08 |
| medium relancé | 1,05 | 0,95 | 0,93 | 0,98 | 1,06 |
| medium 3-beté | 1,02 | 0,98 | 0,97 | 0,99 | 1,02 |
| deep limpé | 1,10 | 0,90 | 0,87 | 0,95 | 1,12 |
| deep relancé | 1,08 | 0,92 | 0,90 | 0,96 | 1,10 |
| deep 3-beté | 1,03 | 0,97 | 0,96 | 0,99 | 1,03 |

**Alternatives écartées.**
- *N'exiger que les contextes atteignables* : plus précis, mais couple le profil à la table de sizings d'une configuration.
- *Tous les facteurs à 1 (équité brute)* : ignore l'avantage de position, que FR-007 demande de modéliser.
- *Valeurs tirées des ordres de grandeur à 100bb* : surestiment l'effet de la position à faible SPR.
- *Dimension « agresseur préflop »* : réelle, mais absente de FR-007. Piste pour la V2, à côté de `hand_category`.

**Conséquences.** Les valeurs terminales du flop (#18) utilisent `pot_type_of`, `flop_positions` et `factor`. Le test de sensibilité (#29, SC-009) fera varier ces valeurs de ± 0,1. Toute modification des valeurs donne une nouvelle version du profil et une nouvelle décision.

---

## D-013 — Flop avec un joueur déjà à tapis : reporté à la V2

- **Date** : 2026-11-27 · **Statut** : Acceptée · **Liens** : FR-007, D-002, D-012, issue #18

**Contexte.** Avec des stacks inégaux, un joueur peut être à tapis alors que deux autres, qui ont encore des jetons, vont au flop (par exemple : stacks 5/10/10, le BTN est à tapis pour 5bb, la SB et la BB paient). Le pot principal se joue alors jusqu'au bout sans décision du joueur à tapis, et le pot annexe se dispute au flop. Aucune règle du modèle ne dit comment combiner l'équité exacte et la réalisation dans ce cas. Avec des stacks égaux (MVP), ce cas n'existe pas : un joueur à tapis met tous les autres à tapis.

**Décision.** Le calcul des valeurs terminales lève une erreur explicite (`NotImplementedError`) sur un terminal de flop dont un joueur vivant est à tapis. Les showdowns avec pots annexes restent entièrement gérés.

**Alternatives écartées.**
- *Réalisation sur tous les pots* : contraire au principe II pour la part à tapis du joueur à court de jetons.
- *Équité exacte sur le pot principal, réalisation sur le pot annexe* : plausible, mais c'est une nouvelle règle du modèle, à décider avec les stacks inégaux.

**Conséquences.** À traiter avec les stacks inégaux (V2), par une nouvelle décision.

---

## D-014 — Paramètres par défaut du Discounted CFR

- **Date** : 2026-11-27 · **Statut** : Acceptée · **Liens** : FR-009, FR-012, issue #19

**Contexte.** Le Discounted CFR (Brown & Sandholm, 2019) dépend de trois paramètres : α (discount des regrets positifs), β (discount des regrets négatifs) et γ (poids de la stratégie moyenne). Ce sont des paramètres de convergence : ils entrent dans l'empreinte d'une solution (FR-012).

**Décision.**
1. **α = 1,5, β = 0, γ = 2**, valeurs recommandées par l'article. À la fin de l'itération t, les regrets cumulés positifs sont multipliés par t^α / (t^α + 1), les négatifs par t^β / (t^β + 1), et la somme des stratégies par (t / (t + 1))^γ.
2. **Mises à jour alternées** dans l'ordre de parole : BTN, SB, BB. Chaque joueur voit la stratégie déjà mise à jour des précédents.

**Alternatives écartées.**
- *CFR+ (regrets négatifs remis à 0 à chaque itération)* : correspond à un cas limite de DCFR (β → −∞), moins performant que les valeurs retenues au poker selon l'article.
- *Mises à jour simultanées* : convergence plus lente en pratique.

**Conséquences.** Les paramètres sont modifiables (`DCFRParams`), et seront enregistrés avec chaque solution (#24).
