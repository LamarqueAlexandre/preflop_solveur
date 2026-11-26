# Plan technique : Solveur préflop Expresso 3-max (MVP)

**Branche** : `001-solveur-preflop-expresso`
**Créé le** : 2026-11-26
**Statut** : Validé
**Entrées** : [constitution.md](constitution.md) v1.0.1, [spec.md](spec.md)

---

## 1. Résumé

Le projet se découpe en trois couches strictement séparées (principe IV) :

- un **moteur** Python autonome qui précalcule les équités, construit l'arbre préflop, résout l'équilibre par Discounted CFR, mesure l'exploitabilité, calcule des meilleures réponses et gère la bibliothèque de solutions ;
- une **API** FastAPI fine qui expose le moteur et les solutions stockées ;
- un **front** React qui affiche et saisit, sans aucun calcul de poker.

Les solutions de la grille 3–25bb sont calculées hors ligne par un batch. Les meilleures réponses sont calculées à la demande.

---

## 2. Arborescence

```
preflop_solveur/
├── engine/                 # bibliothèque Python autonome, sans dépendance web
│   ├── cards/              # cartes, combos (1326), classes (169), grille 13x13
│   ├── evaluator/          # évaluateur 7 cartes rapide + évaluateur de référence naïf
│   ├── equity/             # précalcul et chargement des tenseurs d'équité
│   ├── game/               # config, sizings par tranche, arbre, pots et pots annexes
│   ├── realization/        # profils de réalisation (format versionné)
│   ├── solver/             # Discounted CFR, valeurs terminales, exploitabilité
│   ├── best_response/      # verrouillages, meilleure réponse, comparaison
│   ├── library/            # empreinte, Solution, SolutionStore (abstrait), batch
│   ├── training/           # tirage des spots, perte d'EV, notation
│   └── cli.py              # equity build / solve / batch / sensitivity
├── api/                    # FastAPI : couche fine, aucune logique de poker
├── web/                    # React + TypeScript + Vite + Tailwind
├── tests/
│   ├── engine/
│   └── api/
├── benchmarks/             # benchmarks reproductibles (principe VI)
├── data/                   # tenseurs d'équité et bibliothèque (hors git, régénérables)
└── docs/                   # constitution, spec, plan, decisions, notes/
```

Un seul projet uv contient deux paquets Python, `engine` et `api`. L'API importe l'API publique du moteur, jamais l'inverse. Un test d'architecture vérifie cette règle.

---

## 3. Moteur

### 3.1 Représentation des mains

Les stratégies, ranges et EV sont indexées par les **169 classes** de mains. Ce n'est pas une approximation. Préflop, sans board, deux combos d'une même classe (A♥K♥ et A♠K♠) sont équivalents à une permutation de couleurs près. Le retrait de cartes entre joueurs est porté par les tenseurs d'équité (§ 3.2).

### 3.2 Tenseurs d'équité (FR-006, SC-003)

Pour chaque triplet ordonné de classes (h₁, h₂, h₃), on précalcule une fois :

| Tenseur | Contenu |
|---|---|
| **W** | nombre de triplets de combos compatibles (sans carte commune) : le retrait de cartes |
| **E₃** | équité de chaque joueur dans un pot à 3 (partages inclus) |
| **E₂** | équité de chaque paire de joueurs en tête-à-tête, la main du troisième étant retirée du paquet |

**Pots annexes.** Par linéarité de l'espérance, l'EV d'un joueur s'écrit `pot_principal × E₃ᵢ + pot_annexe_jk × E₂(j vs k | i mort)`. Ces tenseurs suffisent donc à traiter exactement les pots annexes, et donc les stacks inégaux de la V2, sans nouveau précalcul.

**Calcul** (décision D-010, spike [notes/spike-equites.md](notes/spike-equites.md)). Une seule passe : chaque board évalué donne en même temps le résultat à 3 mains et les trois résultats à 2 mains. Méthode : Monte-Carlo simple, avec 450 000 tirages par trio pour respecter SC-003. Le calcul est parallélisé par trio, avec une graine par trio. Le temps de calcul attendu est de 4 à 5 h, avec Numba, sur la machine de développement.

**Évaluateurs.**
- Évaluateur rapide vectorisé en NumPy (`evaluate_batch`), et un noyau Numba testé contre lui pour le calcul des tenseurs (D-010).
- Évaluateur de référence naïf, lent et lisible (meilleure combinaison de 5 cartes parmi 7), testé sur des cas écrits à la main. Il sert de référence indépendante à l'évaluateur rapide.

**Critère SC-003 retenu** (décision D-003) : sur au moins 1 000 triplets de classes, comparés à l'énumération exhaustive, l'écart **moyen** est < 0,1 point et l'écart **maximal** < 0,3 point.

**Stockage.** Environ 135 Mo en float32 dans `data/`, régénérables par `engine equity build`.

### 3.3 Modèle de jeu et arbre (FR-001 à FR-005)

- `GameConfig` est immuable. Elle contient les stacks, les blinds (0,5 / 1bb, sans ante), la table de sizings par tranche (≤ 8bb, 9–15bb, > 15bb), le seuil de conversion en all-in (relance laissant < 1bb derrière) et la référence au profil de réalisation.
- Le constructeur d'arbre suit FR-004 et FR-005, avec les règles complémentaires de la décision D-005.
- Chaque nœud a un **identifiant stable** dérivé du chemin d'actions (ex. `R2.0-F-C`). Il est utilisé par l'API, dans les URL du front et dans le stockage.
- Un résolveur de pots générique pour n joueurs transforme les contributions en pot principal et pots annexes. Il est testé sur des cas calculés à la main et par des tests de propriétés (somme des gains = pot).
- Types de terminaux :
  - fold général ;
  - showdown all-in, toujours à l'équité exacte ;
  - pot qui va au flop, avec réalisation d'équité.

### 3.4 Réalisation d'équité (FR-007, FR-008)

- Le profil est un fichier JSON versionné, indexé par `(position, type_de_pot, nb_joueurs, tranche)`.
  - Positions au flop : à 2 joueurs, en position ou hors de position ; à 3 joueurs, SB = première, BB = milieu, BTN = dernière.
  - Types de pot : limpé, relancé, 3-beté.
- Le format prévoit une clé optionnelle `hand_category`. Les profils existants restent valides quand elle apparaîtra en V2.
- **Normalisation** (décision D-002) : la part de pot d'un joueur vaut `Rᵢ·eqᵢ / Σⱼ Rⱼ·eqⱼ`. Le pot est toujours entièrement redistribué et le jeu reste à somme constante.
- Le profil par défaut est documenté dans `docs/notes/`. Un test vérifie que plus la tranche de profondeur est courte, plus les facteurs sont proches de 1.

### 3.5 Solveur (FR-009 à FR-011)

- **Discounted CFR** (Brown & Sandholm, 2019, *Solving Imperfect-Information Games via Discounted Regret Minimization*), vectorisé sur les 169 mains, avec mises à jour alternées par joueur.
- Valeurs aux terminaux : contractions tensorielles NumPy de W, W·E₃ et W·E₂ avec les reaches des deux autres joueurs. C'est le chemin critique, et il a son benchmark.
- **Exploitabilité** (décision D-001) : **NashConv**, c'est-à-dire la somme sur les trois joueurs de `EV(meilleure réponse) − EV(stratégie actuelle)`, exprimée en % du pot de départ (1,5bb). Une solution est publiable si NashConv < 0,5 %.
  - CFR n'a pas de garantie théorique de convergence vers un équilibre de Nash à 3 joueurs. Ce test est donc le certificat d'équilibre.
- Contenu stocké pour chaque nœud :
  - stratégie moyenne ;
  - EV de chaque action pour chaque main ;
  - reach de chaque joueur (US2, scénario 3).
- **Convention d'EV** (décision D-007) : gain net en bb depuis le début de la main, les blinds postées comptant comme investies.

### 3.6 Meilleure réponse (FR-014 à FR-018)

- Les verrouillages ont la forme `{node_id: stratégie[actions, 169]}`. Aux nœuds non verrouillés, les vilains gardent la stratégie d'équilibre stockée (FR-015).
- Le calcul est une seule remontée de l'arbre, sans itérations. Objectif : moins de 1 s (SC-005 exige moins de 5 s).
- **EV gagnée** (décision D-006) : EV(meilleure réponse contre vilains verrouillés) − EV(stratégie d'équilibre du héros contre ces mêmes vilains). Elle est calculée main par main et au total, en bb/main.
- Le module fournit aussi le texte des limites du calcul (FR-018) :
  - le troisième joueur ne s'adapte pas ;
  - la stratégie est maximalement exploitante ;
  - le résultat dépend du profil de réalisation.

### 3.7 Bibliothèque et batch (FR-012, FR-013, US5)

- **Empreinte** : SHA-256 d'une sérialisation JSON canonique de (config, arbre, profil, paramètres de convergence, version du moteur).
- `SolutionStore` est une interface abstraite (principe VII). L'implémentation MVP utilise un dossier par empreinte contenant :
  - `manifest.json` : métadonnées, exploitabilité, itérations, durée, version, statut conforme / non conforme ;
  - `arrays.npz` : les tableaux de la solution.
  
  Un index SQLite (module standard de Python) sert aux listes.
- Le batch est **idempotent** : il saute une empreinte déjà présente. Il est **reprenable** : chaque solution est écrite de façon atomique (fichier temporaire puis renommage).
- La commande `engine sensitivity` exécute le test de sensibilité (FR-008a, SC-009) et produit un rapport des écarts.

### 3.8 Entraînement (US4)

Le tirage des spots, le calcul de la perte d'EV et la notation sont dans le moteur (`engine/training`), car c'est de la logique de poker. Seuils par défaut, paramétrables (décision D-008) :

| Perte d'EV | Note |
|---|---|
| < 0,05bb | meilleure action |
| de 0,05 à 0,25bb | imprécision |
| ≥ 0,25bb | erreur |

Une action dont la fréquence d'équilibre est non nulle compte comme correcte (US4, scénario 3).

---

## 4. API (FastAPI)

| Route | Rôle |
|---|---|
| `GET /solutions` | liste des solutions conformes |
| `GET /solutions/{hash}/nodes/{node_id}` | stratégie, EV, reaches, résumé du nœud |
| `POST /best-response` → `job_id` | lance une meilleure réponse |
| `GET /jobs/{id}` | état et résultat d'un job |
| `/villain-strategies` (CRUD) | stratégies de vilain enregistrées (FR-017) |
| `/training/sessions` | sessions d'entraînement |

- Les calculs à la demande sont des jobs (principe VII). Pour le MVP, ils tournent dans un exécuteur de processus, et leur état est persisté dans SQLite, pas en mémoire.
- Les types TypeScript du front sont générés depuis le schéma OpenAPI (`openapi-typescript`).
- Tests : pytest avec le client de test de FastAPI (`httpx`).

---

## 5. Front

- Stack : **React + TypeScript + Vite + Tailwind**, TanStack Query pour les appels API, React Router pour la navigation.
- Le chemin du nœud courant est dans l'URL : la navigation se partage, se recharge, et le front n'a pas d'état caché.
- Composants principaux :
  - grille 13×13 (FR-019, FR-020) ;
  - résumé du nœud (FR-021) ;
  - fil d'actions (FR-022) ;
  - éditeur de range (FR-023) ;
  - vue de comparaison (FR-024) ;
  - mode entraînement (FR-025).
- Tests : Vitest et Testing Library, en commençant par la grille 13×13.
- Toute exploitabilité ou EV affichée rappelle qu'elle est relative au modèle et au profil de réalisation (principe II).

---

## 6. Stratégie de validation

| Élément | Référence indépendante |
|---|---|
| Évaluateur rapide | évaluateur naïf et cas écrits à la main |
| Équités (SC-003) | énumération exhaustive sur ≥ 1 000 triplets |
| Règles, pots, pots annexes | cas calculés à la main et tests de propriétés |
| Petits arbres | valeurs calculées à la main |
| Convergence (SC-001) | NashConv < 0,5 % du pot de départ |
| Modèle push/fold (SC-002, voir D-004) | charts heads-up publiés et seconde implémentation indépendante |

---

## 7. Découpage en lots

| Lot | Contenu | Exigences | Validation |
|---|---|---|---|
| 0 | Socle : uv, ruff, mypy strict, pytest, `docs/decisions.md` | — | lint, typage et tests verts |
| 1 | Cartes, combos, classes, grille ; évaluateurs de référence et rapide | FR-006 | cas manuels, croisement des deux évaluateurs |
| 2 | Spike de perf, tenseurs W / E₃ / E₂, `engine equity build` | FR-006, SC-003 | énumération exhaustive |
| 3 | Config, sizings, arbre, résolveur de pots | FR-001 à 005 | TDD, cas calculés à la main |
| 4 | Profils de réalisation, valeurs terminales | FR-007, 008 | petits arbres calculés à la main |
| 5 | Discounted CFR et exploitabilité, **push/fold d'abord** | FR-009, 010 | SC-002 révisé (D-004) |
| 6 | Arbre complet, EV / reach par nœud, empreinte, store, batch | FR-011 à 013, US5 | SC-001, SC-006 (benchmark) |
| 7 | Meilleure réponse, comparaison, test de sensibilité | FR-014 à 016, 008a | SC-005, SC-007, SC-009 |
| 8 | `engine/training` (D-009), puis API | US1 à US4 | TDD pour `engine/training`, tests API |
| 9 | Front : grille et résumé → navigation → éditeur et comparaison → entraînement | FR-019 à 025 | tests de composants, SC-004, SC-008 |

Le batch du lot 6 peut tourner pendant le développement des lots 7 à 9.

---

## 8. Dépendances validées

- **Python (runtime)** : `numpy`, `fastapi`, `uvicorn`, `pydantic`. `numba` (justifié par le spike du lot 2, décision D-010 ; ajouté à l'issue #10).
- **Python (dev)** : `pytest`, `pytest-benchmark`, `hypothesis`, `httpx`, `ruff`, `mypy`.
- **Front** : `react`, `react-dom`, `react-router`, `@tanstack/react-query`, `tailwindcss`, `vite`, `typescript`, `vitest`, `@testing-library/react`, `jsdom`, `openapi-typescript`.

---

## 9. Décisions prises lors du plan

Ces décisions sont consignées, avec leur contexte et les alternatives écartées, dans le journal [decisions.md](decisions.md), qui fait foi. Les décisions suivantes (D-009 et au-delà) n'y figurent que là.

- **D-001 — Mesure d'exploitabilité** : NashConv (somme des gains de meilleure réponse des trois joueurs), en % du pot de départ (1,5bb). Seuil de publication : 0,5 %.
- **D-002 — Normalisation de la réalisation** : la part de pot d'un joueur vaut `Rᵢ·eqᵢ / Σⱼ Rⱼ·eqⱼ`, pour que le pot soit toujours entièrement redistribué.
- **D-003 — Précision des équités (SC-003)** : écart moyen < 0,1 point et écart maximal < 0,3 point, sur ≥ 1 000 triplets de classes, contre l'énumération exhaustive.
- **D-004 — Validation push/fold sans chart 3-max (révision de SC-002)** : aucune chart de Nash push/fold 3-max chipEV n'est disponible. SC-002 est remplacé par trois validations :
  1. **Sous-cas heads-up** : le BTN est forcé à folder ; les ranges SB / BB sont comparées aux charts de Nash push/fold heads-up chipEV publiées, sur au moins trois profondeurs, avec moins de 2 % d'écart en fréquence.
  2. **Implémentation indépendante** : un *fictitious play* écrit séparément sur l'arbre push/fold 3-max ; moins de 2 % d'écart en fréquence de push avec le solveur principal, sur au moins trois profondeurs.
  3. **Certificat d'équilibre** : NashConv < 0,5 % du pot de départ.
- **D-005 — Règles d'arbre complémentaires à FR-004** :
  - face à une relance d'isolation, le joueur dispose du jeu d'actions « face à une relance » de sa tranche ;
  - un limper relancé peut sur-relancer ;
  - au plus un 4-bet, toujours all-in.
- **D-006 — EV gagnée par la meilleure réponse** : EV(meilleure réponse contre vilains verrouillés) − EV(équilibre du héros contre ces mêmes vilains).
- **D-007 — Convention d'EV** : gain net en bb depuis le début de la main, blinds postées comptées comme investies.
- **D-008 — Notation de l'entraînement** : meilleure action si perte < 0,05bb, imprécision de 0,05 à 0,25bb, erreur si perte ≥ 0,25bb. Seuils paramétrables.

---

## 10. Conformité à la constitution

| Principe | Mise en œuvre |
|---|---|
| I. Exactitude du modèle | lots 1 à 4 en TDD avant tout solveur ; chaque règle a son test |
| II. Hypothèses explicites | profil référencé dans chaque solution ; équité exacte en all-in ; mention « relatif au modèle » partout |
| III. Reproductibilité | empreinte de configuration et version du moteur dans le manifeste |
| IV. Séparation | arborescence § 2 ; logique de l'entraînement dans le moteur ; test d'architecture |
| V. Validation | § 6 ; statut non conforme pour les solutions hors seuil |
| VI. Performance mesurée | `benchmarks/` ; Numba conditionné au spike du lot 2 |
| VII. Prêt pour le SaaS | `SolutionStore` abstrait ; jobs persistés ; pas d'état global dans l'API |
