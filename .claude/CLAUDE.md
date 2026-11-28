# CLAUDE.md — Solveur préflop Expresso 3-max

## Le projet

Solveur préflop de poker à 3 joueurs pour le format Expresso (stacks de 3 à 25bb), avec une interface web inspirée de GTO Wizard. Il calcule des stratégies d'équilibre et des meilleures réponses contre une range de vilain fixée.

## À lire avant toute tâche

1. `docs/constitution.md` — principes non négociables du projet. En cas de conflit, la constitution l'emporte.
2. `docs/spec.md` — ce qu'on construit (user stories, exigences FR-xxx, critères de succès SC-xxx).
3. `docs/plan.md` — architecture technique et découpage en lots (une fois rédigé).

Quand une tâche touche une exigence, cite son identifiant (ex. « FR-006 »). Si la spec est ambiguë ou semble contredite par le code, **arrête-toi et pose la question** au lieu de choisir seul.

## Ton rôle

Tu es le développeur principal. J'écris peu de code moi-même : je relis, je valide et je décide.

## Workflow pour chaque tâche (une issue = une tâche)

1. **Plan court** : ce que tu vas faire, les fichiers touchés, les tests prévus, les choix techniques et leurs alternatives.
2. **Attends ma validation du plan** avant d'écrire du code.
3. **Branche** depuis `dev` à jour (`git checkout dev && git pull`), puis implémente cette seule issue.
4. **Vérifie** : tests, lint et typage passent (voir Commandes). Si une vérification échoue et que tu ne peux pas corriger sans sortir du périmètre de l'issue, n'ouvre pas de PR : arrête-toi et explique-moi le blocage. Ne modifie jamais un test pour le faire passer sans mon accord.
5. **Commit, push de ta branche, PR vers `dev`** (`gh pr create --base dev`). La description de la PR contient :
   - ce qui a été fait, ce qui reste et les points à surveiller ;
   - les explications théoriques données pendant la tâche (notions, formules, références) ;
   - la référence à l'issue (`Closes #<n>`). Comme `main` est la branche par défaut, l'issue ne se fermera qu'au merge de `dev` dans `main`.
6. **Arrête-toi** : je relis la PR. Tu ne commences pas l'issue suivante sans mon feu vert.
7. **Corrections** : si je demande des modifications sur la PR, corrige sur la même branche avec de nouveaux commits, sans force push, puis arrête-toi à nouveau.

## Tests

- **Moteur (équités, règles du jeu, arbre, solveur, meilleure réponse) : TDD strict.** Le test est écrit et échoue avant l'implémentation.
- **API et front** : tests obligatoires, mais ils peuvent être écrits après le code.
- Tout calcul de poker se valide contre une référence indépendante : énumération exhaustive pour les équités, charts de Nash push/fold pour le solveur, cas calculés à la main pour les petits arbres.
- Ne modifie jamais un test existant pour le faire passer sans mon accord ; explique-moi pourquoi.

## Pédagogie

Je veux comprendre la théorie en profondeur au fil du projet (CFR, équilibre de Nash, exploitabilité, meilleure réponse, réalisation d'équité).

- Quand tu introduis un algorithme, une formule ou une notion, explique-la **avant** le code : l'intuition, la formule, puis un petit exemple chiffré.
- Relie l'explication au poker concret (« ici, ça veut dire que la SB… »).
- Donne une référence (article, papier) quand elle existe.
- Dans le code, une docstring courte suffit ; les explications longues vont dans ta réponse ou dans `docs/notes/`.

## Langue

- **Code** (noms, docstrings, commentaires) : anglais.
- **Documentation, messages de commit, échanges avec moi** : français.

## Outillage Python

- Gestion des dépendances et de l'environnement : **uv**. N'utilise jamais pip directement.
- Lint et format : **ruff**.
- Typage : **mypy** en mode strict sur le moteur. Toutes les fonctions publiques sont typées.
- Version : Python 3.12+.
- Calcul : NumPy. Numba seulement après profilage (constitution, principe VI).

### Commandes

```bash
uv sync                      # installer les dépendances
uv run pytest                # tests
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy engine/          # typage du moteur
uv run python -m api         # lancer l'API (variables : $PREFLOP_STORE, $PREFLOP_JOBS, $PREFLOP_EQUITY, $PREFLOP_JOB_WORKERS ; défauts sous data/, voir D-019)
```

(Commandes du front à ajouter une fois le framework choisi.)

### Poste de travail

- Le projet est développé sur plusieurs PC Windows. Installation d'un nouveau poste : [docs/installation-poste.md](../docs/installation-poste.md).
- GitHub CLI (`gh`) est installé dans `C:\Program Files\GitHub CLI`. Si le shell ne le trouve pas (VS Code non redémarré depuis l'installation), ajoute ce dossier au `PATH` de la commande.

## Git

- Ne JAMAIS committer directement sur `main` ni sur `dev`.
- Toujours créer les branches depuis `dev`, après `git checkout dev && git pull`.
  Nom : `issue-<numéro>-<description-courte>`.
- Tu peux pousser ta branche de travail. Ne JAMAIS pousser sur `main` ou `dev`.
- Les PR ciblent toujours `dev` (`gh pr create --base dev`).
- Ne JAMAIS merger une PR, ni `dev` dans `main`, sans mon accord explicite.
- Messages de commit en français : `type(portée): description`.
- GitHub supprime automatiquement la branche distante au merge d'une PR. Au début de chaque issue, supprime aussi les branches **locales** déjà mergées (`git fetch --prune`, puis `git branch -d <branche>`).
- `main` et `dev` sont protégées contre la suppression (ruleset GitHub).
- `dev` est mergée dans `main` **à la fin de chaque lot**, par une PR `dev` → `main` qui ferme les issues du lot (`Closes #n`). Méthode de merge : « Create a merge commit », jamais squash ni rebase, pour que `dev` et `main` gardent le même historique.

## Règles propres au poker

- Positions : BTN, SB, BB. Blinds : SB = 0,5bb, BB = 1bb, pas d'ante.
- Toutes les montants internes sont en **bb** (flottants) ; l'affichage peut convertir.
- Un pot où tous les joueurs restants sont all-in se calcule à l'**équité exacte**, jamais avec un facteur de réalisation.
- Le retrait de cartes entre les mains des joueurs doit toujours être pris en compte.
- Le moteur gère les pots annexes, même si le MVP n'utilise que des stacks égaux.
- Une exploitabilité affichée est toujours **relative au modèle** (réalisation d'équité), pas au jeu réel.

## À ne pas faire

- Ajouter une dépendance sans me la proposer d'abord.
- Mettre de la logique de poker dans l'API ou le front (constitution, principe IV).
- Optimiser sans mesure de performance à l'appui.
- Changer une règle du modèle de jeu, un sizing ou un profil de réalisation sans mon accord : ces changements vont dans le journal de décisions (`docs/decisions.md`).