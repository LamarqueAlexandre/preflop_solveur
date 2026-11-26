# Spécification fonctionnelle : Solveur préflop Expresso 3-max (MVP)

**Branche** : `001-solveur-preflop-expresso`
**Créée le** : 2026-11-26
**Statut** : Validée
**Demande initiale** : « Un solveur préflop de poker à 3 joueurs pour le format Expresso, avec une interface graphique inspirée de GTO Wizard, qui me permet d'étudier les stratégies d'équilibre et de construire des ranges exploitantes en fonction de la range de vilain. »

---

## Scénarios utilisateur et tests *(obligatoire)*

### User story 1 — Consulter la stratégie d'équilibre d'un spot (Priorité : P1)

En tant que joueur d'Expresso, je choisis une profondeur de stack et un spot (par exemple « BTN, premier à parler, 15bb »). Je vois la stratégie d'équilibre sur une grille 13x13 : pour chaque main, la fréquence de chaque action et son EV.

**Pourquoi cette priorité** : c'est la valeur de base du produit. Sans solutions consultables, aucune autre fonctionnalité n'a de sens.

**Test indépendant** : générer la solution d'une seule profondeur de stack, ouvrir le spot d'ouverture du BTN et vérifier que la grille affiche des fréquences cohérentes et que l'exploitabilité est inférieure au seuil.

**Scénarios d'acceptation** :
1. **Étant donné** une bibliothèque contenant la solution à 15bb, **quand** je sélectionne 15bb et le spot d'ouverture du BTN, **alors** la grille 13x13 affiche pour chaque main la répartition des actions disponibles (couleur par action, proportions des stratégies mixtes).
2. **Étant donné** une grille affichée, **quand** je survole une main, **alors** je vois la fréquence de chaque action, l'EV de chaque action en bb et le nombre de combinaisons.
3. **Étant donné** une grille affichée, **quand** je consulte le résumé du spot, **alors** je vois la fréquence globale de chaque action sur toute la range, l'exploitabilité de la solution et le profil de réalisation utilisé.
4. **Étant donné** une profondeur absente de la bibliothèque, **quand** je la demande, **alors** l'interface indique qu'elle n'est pas calculée et propose la profondeur disponible la plus proche.

---

### User story 2 — Naviguer dans l'arbre d'actions (Priorité : P2)

Je navigue dans l'arbre préflop en cliquant sur les actions successives (BTN raise 2x → SB 3-bet all-in → BB…). À chaque nœud, la grille montre la stratégie du joueur qui parle, appliquée à sa range à ce moment-là.

**Pourquoi cette priorité** : l'ouverture seule ne suffit pas. Les décisions face à une relance représentent l'essentiel de l'étude.

**Test indépendant** : sur une solution, parcourir trois nœuds successifs, revenir en arrière via le fil d'actions et vérifier que les ranges affichées sont cohérentes avec les actions précédentes.

**Scénarios d'acceptation** :
1. **Étant donné** le spot d'ouverture du BTN, **quand** je clique sur « Raise 2x », **alors** l'interface passe au nœud de la SB et affiche sa stratégie face à cette relance.
2. **Étant donné** un nœud profond, **quand** je clique sur un élément du fil d'actions, **alors** je reviens à ce nœud.
3. **Étant donné** un nœud, **quand** j'affiche la range d'un joueur, **alors** seules les mains qui ont atteint ce nœud apparaissent, pondérées par leur fréquence d'arrivée.
4. **Étant donné** un nœud terminal (fold général, all-in payé), **quand** je l'atteins, **alors** l'interface affiche le résultat du pot et l'EV des joueurs concernés.

---

### User story 3 — Construire une range exploitante contre la range de vilain (Priorité : P3)

À un ou plusieurs nœuds de l'arbre, je fixe la stratégie réelle d'un vilain (par exemple « le BTN ouvre 80 % à 2x »). L'outil calcule ma meilleure réponse et me montre l'écart avec la stratégie d'équilibre, ainsi que l'EV gagnée.

**Pourquoi cette priorité** : en micro-limites, les adversaires s'écartent fortement de l'équilibre. Exploiter ces écarts est le principal levier de gain.

**Test indépendant** : fixer l'ouverture du BTN à 100 % à 15bb, calculer la meilleure réponse de la SB et vérifier que sa range de 3-bet all-in s'élargit par rapport à l'équilibre, avec un gain d'EV positif.

**Scénarios d'acceptation** :
1. **Étant donné** un nœud où parle un vilain, **quand** j'ouvre l'éditeur de range, **alors** je peux définir, pour chaque main, la fréquence de chaque action disponible (clic sur la grille, pinceau de fréquence, raccourcis « top X % »).
2. **Étant donné** une stratégie de vilain fixée, **quand** je lance le calcul en choisissant le joueur héros, **alors** j'obtiens en moins de 5 secondes la stratégie de meilleure réponse du héros dans tous les nœuds où il parle après le nœud fixé.
3. **Étant donné** une meilleure réponse calculée, **quand** j'affiche la vue de comparaison, **alors** je vois, main par main, l'écart de fréquence avec l'équilibre et l'EV gagnée, ainsi que l'EV totale gagnée en bb/main.
4. **Étant donné** une meilleure réponse calculée, **quand** je la consulte, **alors** un avertissement rappelle que le troisième joueur reste à l'équilibre et ne s'adapte pas, et que la stratégie obtenue est maximalement exploitante.
5. **Étant donné** une range de vilain que j'utilise souvent, **quand** je l'enregistre sous un nom, **alors** je peux la réutiliser plus tard sur d'autres spots et d'autres profondeurs.

---

### User story 4 — S'entraîner sur des spots (Priorité : P4)

Je lance une session d'entraînement : l'outil me présente des spots tirés de la bibliothèque (position, stack, main, actions précédentes). Je choisis une action et j'obtiens un retour basé sur la perte d'EV par rapport à la meilleure action.

**Pourquoi cette priorité** : consulter des grilles ne suffit pas à mémoriser les stratégies. L'entraînement transforme l'étude en réflexes.

**Test indépendant** : lancer une session de 20 spots filtrée sur la SB entre 10 et 15bb, répondre à tous et vérifier le score et le détail de chaque erreur.

**Scénarios d'acceptation** :
1. **Étant donné** des filtres (positions, plage de stacks, types de spots), **quand** je lance une session, **alors** les spots tirés respectent ces filtres.
2. **Étant donné** un spot présenté, **quand** je choisis une action, **alors** l'outil affiche la stratégie d'équilibre pour cette main, la perte d'EV de mon choix en bb et une note (meilleure action / imprécision / erreur).
3. **Étant donné** une main jouée en stratégie mixte, **quand** je choisis une action dont la fréquence d'équilibre n'est pas nulle, **alors** la réponse est comptée comme correcte (perte d'EV ≈ 0).
4. **Étant donné** une session terminée, **quand** j'affiche le bilan, **alors** je vois le score, la perte d'EV totale et moyenne, et la liste des erreurs, en pouvant ouvrir chaque spot dans la vue stratégie.

---

### User story 5 — Générer la bibliothèque de solutions (Priorité : P1, prérequis technique)

En tant que développeur et utilisateur, je lance un batch qui calcule toutes les solutions de la grille de stacks avec une configuration donnée (arbre, profil de réalisation, seuil de convergence) et les enregistre dans la bibliothèque.

**Pourquoi cette priorité** : les user stories 1, 2 et 4 lisent cette bibliothèque.

**Test indépendant** : lancer le batch sur deux profondeurs, vérifier que deux solutions sont stockées avec leur empreinte de configuration et leur rapport d'exploitabilité.

**Scénarios d'acceptation** :
1. **Étant donné** une configuration, **quand** je lance le batch, **alors** chaque profondeur de la grille est résolue et stockée avec son empreinte, son exploitabilité, son nombre d'itérations et sa durée de calcul.
2. **Étant donné** une solution déjà présente avec la même empreinte, **quand** je relance le batch, **alors** elle n'est pas recalculée.
3. **Étant donné** une résolution qui n'atteint pas le seuil d'exploitabilité dans la limite d'itérations, **quand** le batch se termine, **alors** la solution est marquée non conforme et n'apparaît pas dans l'interface.
4. **Étant donné** un batch interrompu, **quand** je le relance, **alors** il reprend aux profondeurs non encore calculées.

---

### Cas limites

- **All-in avant le flop** : l'EV se calcule sur l'équité exacte, sans facteur de réalisation, y compris pour les pots à trois joueurs avec pots annexes. Avec des stacks égaux au MVP, il n'y a pas de pot annexe ; le cas doit quand même être géré par le moteur en prévision des stacks inégaux.
- **Relance qui engage la quasi-totalité du stack** : si un sizing laisse moins d'un seuil de stack derrière (par exemple < 1bb), il est remplacé par un all-in.
- **SB complète et BB checke** : pot limpé à deux ou trois joueurs, avec réalisation propre à ce type de pot.
- **Fold du BTN et de la SB** : la BB gagne les blinds, sans décision.
- **Main bloquée par le retrait de cartes** : dans l'éditeur de range et l'affichage, le nombre de combinaisons tient compte des cartes retirées par les actions précédentes uniquement s'il y a des cartes connues (non applicable au MVP sauf en drill, où la main du héros retire des combinaisons aux vilains).
- **Range de vilain vide à un nœud** (fréquence 0 pour toutes les mains d'une action) : le nœud enfant est inatteignable ; l'interface le grise au lieu d'afficher une grille vide.
- **Stratégie de vilain incomplète dans l'éditeur** (fréquences d'une main qui ne totalisent pas 100 %) : l'éditeur refuse la validation et signale les mains concernées.

---

## Exigences *(obligatoire)*

### Exigences fonctionnelles — Modèle de jeu

- **FR-001** : Le système DOIT modéliser une table à 3 joueurs (BTN, SB, BB) au format Expresso, sans rake, en chipEV.
- **FR-002** : Le système DOIT utiliser une structure de blinds SB = 0,5bb, BB = 1bb, sans ante.
- **FR-003** : Le système DOIT résoudre des configurations à stacks égaux pour les trois joueurs, sur une grille fixe de 3 à 25bb avec un pas de 1bb (23 solutions).
- **FR-004** : Le système DOIT permettre de définir les sizings disponibles par tranche de profondeur. Configuration par défaut :
  - **≤ 8bb** : ouverture fold / limp / all-in ; face à une relance : fold / call / all-in.
  - **9 à 15bb** : ouverture fold / limp / min-raise (2x) / all-in ; face à une relance : fold / call / 3-bet all-in.
  - **> 15bb** : ouverture fold / limp / 2x / 2,5x / all-in ; face à une relance : fold / call / 3-bet à 3x la relance / all-in ; face à un 3-bet : fold / call / 4-bet all-in.
  - **Relance d'isolation face à un ou deux limps** : all-in à ≤ 8bb ; 3bb + 1bb par limper supplémentaire ou all-in au-delà.
- **FR-005** : Le système DOIT inclure l'open-limp du BTN et la complète de la SB, à toutes les profondeurs. Face à un ou deux limps, chaque joueur qui parle dispose de : fold (sauf BB) / check ou complète / relance d'isolation / all-in.
- **FR-006** : Le système DOIT calculer les équités préflop à deux et à trois mains en tenant compte du retrait de cartes entre les mains, sur les 169 classes de mains et leurs combinaisons.
- **FR-007** : Le système DOIT appliquer, aux pots qui vont au flop sans all-in général, un facteur de réalisation d'équité qui dépend de quatre dimensions : la position au flop (en position / hors de position, ou position relative à 3 joueurs), le type de pot (limpé, relancé, 3-beté), le nombre de joueurs au flop (2 ou 3) et la tranche de profondeur (≤ 8bb, 9 à 15bb, > 15bb, comme pour les sizings).
- **FR-008** : Le système DOIT fournir un profil de réalisation par défaut, documenté, et permettre d'en créer d'autres. Chaque solution référence le profil utilisé. Au MVP, un facteur s'applique à toutes les mains d'un même contexte. Le profil par défaut DOIT respecter la règle suivante : plus la tranche de profondeur est courte, plus les facteurs se rapprochent de 1. Le format du profil DOIT pouvoir accueillir plus tard une dimension « catégorie de main » sans changer les profils existants.
- **FR-008a** : Le système DOIT fournir un test de sensibilité au profil de réalisation : résoudre une même configuration avec deux profils différents et produire un rapport des écarts de stratégie (écart de fréquence moyen et maximal par nœud, mains qui changent d'action majoritaire).

### Exigences fonctionnelles — Résolution

- **FR-009** : Le système DOIT calculer une stratégie d'équilibre pour les trois joueurs sur l'arbre préflop complet d'une configuration.
- **FR-010** : Le système DOIT mesurer l'exploitabilité de chaque solution, exprimée en pourcentage du pot de départ, et ne publier que les solutions dont l'exploitabilité est inférieure à 0,5 %.
- **FR-011** : Le système DOIT calculer et stocker, pour chaque nœud et chaque main, la fréquence de chaque action et l'EV de chaque action.
- **FR-012** : Le système DOIT identifier chaque solution par l'empreinte de sa configuration (stacks, blinds, arbre, profil de réalisation, paramètres de convergence, version du moteur).
- **FR-013** : Le système DOIT fournir un batch de génération de la bibliothèque, idempotent et reprenable.

### Exigences fonctionnelles — Meilleure réponse

- **FR-014** : Le système DOIT permettre de fixer la stratégie d'un ou des deux vilains à un ou plusieurs nœuds d'une solution existante.
- **FR-015** : Aux nœuds non fixés, les vilains DOIVENT conserver leur stratégie d'équilibre.
- **FR-016** : Le système DOIT calculer à la demande la meilleure réponse du joueur héros choisi et la comparer à sa stratégie d'équilibre (écart de fréquence et EV gagnée, par main et au total).
- **FR-017** : Le système DOIT permettre d'enregistrer, nommer et réutiliser des stratégies de vilain.
- **FR-018** : Le système DOIT afficher, avec chaque meilleure réponse, les limites du calcul (troisième joueur non adaptatif, stratégie maximalement exploitante, dépendance au profil de réalisation).

### Exigences fonctionnelles — Interface

- **FR-019** : L'interface DOIT afficher une grille 13x13 (paires sur la diagonale, suited au-dessus, offsuit en dessous) avec, pour chaque case, la répartition colorée des actions.
- **FR-020** : L'interface DOIT afficher au survol d'une main : fréquences, EV par action, nombre de combinaisons.
- **FR-021** : L'interface DOIT afficher un résumé par nœud : fréquences globales des actions, taille de range, exploitabilité de la solution, profil de réalisation.
- **FR-022** : L'interface DOIT permettre de naviguer dans l'arbre par un fil d'actions cliquable et de revenir à n'importe quel nœud précédent.
- **FR-023** : L'interface DOIT fournir un éditeur de range (sélection par clic, pinceau de fréquence, raccourcis « top X % », effacer, inverser).
- **FR-024** : L'interface DOIT fournir une vue de comparaison entre deux stratégies (équilibre / meilleure réponse) au niveau de la main et au niveau global.
- **FR-025** : L'interface DOIT fournir un mode entraînement avec filtres, notation par perte d'EV et bilan de session.

### Hors périmètre du MVP

- Postflop (le postflop est modélisé uniquement par la réalisation d'équité).
- Stacks inégaux (prévu en V2 ; le moteur doit gérer les pots annexes dès le MVP).
- Node locking avec recalcul de l'équilibre des autres joueurs (V2).
- ICM et modèles de prize pool (Expresso modélisé en winner-takes-all).
- Comptes utilisateurs, abonnement, paiement.
- Import d'historiques de mains.
- Situations à 2 joueurs (après élimination).
- Application mobile.

### Entités clés

- **Configuration de jeu** : blinds, stacks, éventuelles antes, définition de l'arbre (sizings par tranche), profil de réalisation, paramètres de convergence.
- **Arbre d'actions** : ensemble des nœuds préflop d'une configuration.
- **Nœud** : joueur qui parle, actions possibles, état du pot et des stacks, nœud parent.
- **Solution** : stratégies et EV de tous les joueurs à tous les nœuds pour une configuration, avec empreinte, exploitabilité, version du moteur, date et durée de calcul.
- **Stratégie** : pour un joueur à un nœud, fréquence de chaque action pour chaque main.
- **Range** : poids de chaque main pour un joueur à un nœud donné.
- **Profil de réalisation** : ensemble nommé et versionné de facteurs de réalisation d'équité.
- **Verrouillage** : stratégie imposée à un vilain à un nœud, nommée et réutilisable.
- **Meilleure réponse** : stratégie du héros calculée contre un ensemble de verrouillages, avec EV gagnée par rapport à l'équilibre.
- **Session d'entraînement** : filtres, spots tirés, réponses, pertes d'EV, score.

---

## Critères de succès *(obligatoire)*

### Résultats mesurables

- **SC-001** : 100 % des solutions publiées dans la bibliothèque ont une exploitabilité inférieure à 0,5 % du pot de départ.
- **SC-002** : En configuration push/fold pur, la solution est validée de trois façons (aucune chart de Nash push/fold 3-max chipEV n'étant disponible, voir décision D-004) :
  1. **Sous-cas heads-up** : le BTN étant forcé à folder, les ranges de la SB et de la BB correspondent aux charts de Nash push/fold heads-up chipEV publiées, avec moins de 2 % d'écart en fréquence, pour au moins trois profondeurs testées.
  2. **Implémentation indépendante** : les ranges du solveur et celles d'un *fictitious play* écrit séparément sur l'arbre push/fold 3-max diffèrent de moins de 2 % en fréquence de push sur l'ensemble des mains, pour au moins trois profondeurs testées.
  3. **Certificat d'équilibre** : l'exploitabilité (NashConv) est inférieure à 0,5 % du pot de départ.
- **SC-003** : Sur un échantillon d'au moins 1 000 confrontations à trois mains (triplets de classes), les équités du moteur diffèrent de l'énumération exhaustive de moins de 0,1 point de pourcentage **en moyenne** et de moins de 0,3 point **au maximum** (voir décision D-003).
- **SC-004** : L'affichage de la grille d'un nœud prend moins d'une seconde après la sélection.
- **SC-005** : Une meilleure réponse est calculée et affichée en moins de 5 secondes.
- **SC-006** : La génération de la bibliothèque complète (23 solutions) tient en une nuit (moins de 10 heures) sur le PC de développement. La configuration exacte de la machine est relevée lors du premier benchmark.
- **SC-007** : Dans le test de référence de la user story 3 (BTN ouvre 100 % à 15bb), la meilleure réponse de la SB produit un gain d'EV positif et une range d'all-in plus large qu'à l'équilibre.
- **SC-008** : Une session d'entraînement de 20 spots se joue sans temps de chargement perceptible entre deux spots (moins de 300 ms).
- **SC-009** : Le test de sensibilité est exécuté sur au moins trois profondeurs (une par tranche) en faisant varier les facteurs du profil par défaut de ± 0,1. Son rapport sert à décider si la calibration par catégorie de main est prioritaire pour la V2.

---

## Clarifications

### Session 2026-11-26

- Q : Faut-il modéliser des antes ? → R : Non, blinds seules (FR-002).
- Q : Bornes et pas de la grille de stacks ? → R : 3 à 25bb, pas de 1bb (FR-003).
- Q : Sizings par tranche de profondeur ? → R : configuration proposée retenue (FR-004).
- Q : Le BTN peut-il open-limper ? → R : Oui, à toutes les profondeurs, avec relance d'isolation pour les joueurs suivants (FR-004, FR-005).
- Q : Granularité du profil de réalisation ? → R : position × type de pot × nombre de joueurs au flop × tranche de profondeur au MVP ; dimension « catégorie de main » reportée en V2, sa priorité étant décidée par un test de sensibilité (FR-007, FR-008, FR-008a, SC-009).
- Q : Machine de calcul de la bibliothèque ? → R : hypothèse retenue : PC de développement, à confirmer au premier benchmark (SC-006).
- Q : Quelle référence pour valider le push/fold, faute de chart de Nash 3-max chipEV ? → R : sous-cas heads-up comparé aux charts publiées, implémentation indépendante par *fictitious play* et certificat d'exploitabilité (SC-002 révisé, décision D-004 du plan).
- Q : SC-003 vise-t-il un écart moyen ou maximal ? → R : les deux : écart moyen < 0,1 point et écart maximal < 0,3 point (SC-003 révisé, décision D-003).