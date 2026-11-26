# Constitution — Solveur préflop Expresso 3-max

## Principes fondamentaux

### I. Exactitude du modèle de jeu avant tout
Les règles du jeu modélisé (positions BTN/SB/BB, blinds, ordre de parole, tailles de relance, all-in, retrait de cartes) sont implémentées et testées **avant** toute optimisation ou interface. Un résultat juste et lent vaut mieux qu'un résultat rapide et faux. Toute règle du jeu modélisé a au moins un test unitaire.

### II. Hypothèses explicites, jamais cachées
Le solveur ne joue pas le postflop : il s'appuie sur des **facteurs de réalisation d'équité**. Ces facteurs :
- sont paramétrables, versionnés et visibles dans l'interface pour chaque solution ;
- ne s'appliquent jamais aux pots où tous les joueurs restants sont all-in (on prend l'équité exacte) ;
- sont rappelés partout où une EV ou une exploitabilité est affichée.

L'exploitabilité mesurée l'est **par rapport au modèle simplifié**, pas au jeu réel. Toute documentation ou interface qui affiche une exploitabilité doit le dire.

### III. Reproductibilité
Une solution est identifiée de manière unique par l'empreinte (hash) de sa configuration : stacks, blinds, arbre d'actions, profil de réalisation, paramètres de convergence et version du moteur. La même configuration produit la même solution. Une solution calculée avec une ancienne version du moteur reste lisible et indique sa version.

### IV. Séparation stricte moteur / API / front
- **Moteur** : bibliothèque Python autonome, sans dépendance web, utilisable en ligne de commande et dans des tests.
- **API** : couche fine qui expose le moteur et les solutions stockées, sans logique de poker.
- **Front** : affichage et saisie uniquement. Le front ne calcule jamais de stratégie ni d'EV.

### V. Validation contre des références connues
- Les équités à 3 mains sont vérifiées par énumération exhaustive sur un échantillon.
- Les solutions en push/fold pur sont validées de trois façons, faute de chart de Nash push/fold 3-max chipEV publiée (décision D-004) :
  - sous-cas heads-up (BTN forcé à folder) comparé aux charts de Nash push/fold heads-up chipEV publiées ;
  - comparaison à une implémentation indépendante (*fictitious play*) sur l'arbre push/fold 3-max ;
  - certificat d'équilibre : exploitabilité sous le seuil de publication.
- L'exploitabilité est calculée et stockée à chaque résolution. Une solution qui ne respecte pas le seuil n'est pas publiée dans la bibliothèque.

### VI. Performance mesurée, pas supposée
Les chemins critiques (tables d'équité, itérations CFR, meilleure réponse) ont des benchmarks reproductibles. On n'optimise (vectorisation NumPy, Numba, parallélisme) qu'après profilage. Toute régression de performance > 20 % sur un benchmark doit être justifiée.

### VII. Prêt pour le SaaS, sans le construire
Le MVP est mono-utilisateur, sans authentification. Mais on évite ce qui bloquerait un passage multi-utilisateurs : pas d'état global en mémoire côté API, stockage des solutions derrière une interface abstraite, calculs à la demande pensés comme des tâches asynchrones.

## Contraintes techniques

- **Moteur** : Python 3.12+, NumPy, Numba si le profilage le justifie.
- **API** : FastAPI.
- **Front** : application web (Vite, TypeScript, Tailwind). Le framework est choisi à l'étape du plan.
- **Tests** : pytest pour le moteur et l'API ; tests de composants pour la grille 13x13.
- **Calcul** : solutions de la grille de stacks précalculées offline par un batch ; les meilleures réponses sont calculées à la demande.
- **Valeur** : chipEV uniquement au MVP.

## Workflow de développement

- Chaque fonctionnalité suit le cycle spec-kit : `specify` → `clarify` → `plan` → `tasks` → `implement`.
- Les tests du moteur sont écrits avant l'implémentation des règles de jeu et des calculs d'équité (principe I).
- Aucune solution n'entre dans la bibliothèque sans son rapport d'exploitabilité (principe V).
- Les décisions qui modifient le modèle de jeu (nouveau sizing, nouvelle règle, nouveau profil de réalisation) sont consignées dans le journal de décisions ([decisions.md](decisions.md)).

## Gouvernance

Cette constitution prévaut sur les autres pratiques du projet. Toute modification est datée, justifiée et versionnée (versionnage sémantique : MAJEUR si un principe est retiré ou redéfini, MINEUR si un principe est ajouté, PATCH pour les clarifications). Les plans et les tâches doivent vérifier leur conformité aux principes I à VII.

**Version** : 1.0.1 | **Ratifiée** : 2026-11-26 | **Dernière modification** : 2026-11-26

### Historique des modifications

| Version | Date | Modification | Justification |
|---|---|---|---|
| 1.0.1 (PATCH) | 2026-11-26 | Principe V : la comparaison à des charts push/fold 3-max publiées est remplacée par les trois validations de D-004. | Aucune chart de Nash push/fold 3-max chipEV n'est disponible. L'esprit du principe (valider contre des références connues) est inchangé ; seule une référence inexistante est corrigée. |
| 1.0.0 | 2026-11-26 | Ratification. | — |