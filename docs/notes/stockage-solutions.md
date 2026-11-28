# Empreinte et stockage des solutions

Note liée à FR-012, FR-013, aux principes III et VII et à D-016 (issue #24). Code : `engine/library/fingerprint.py`, `serialization.py`, `store.py`.

## 1. Pourquoi une empreinte

Une solution dépend de tout ce qui entre dans le calcul :
- la config : stacks, blinds, sizings, seuil d'all-in ;
- l'arbre ;
- le profil de réalisation ;
- les paramètres de convergence ;
- la version du moteur ;
- les tenseurs d'équité.

L'empreinte résume tout ça en 64 caractères hexadécimaux. Si deux calculs ont la même empreinte, ils ont les mêmes entrées. Si une seule entrée change, l'empreinte change. C'est le principe III (reproductibilité). C'est aussi ce qui rend le batch idempotent : une empreinte déjà présente dans le store, c'est une solution déjà calculée.

## 2. SHA-256 et JSON canonique

  empreinte = SHA-256( JSON canonique des entrées )

SHA-256 (NIST FIPS 180-4) est déterministe. Changer un seul bit de l'entrée change environ la moitié des bits du résultat, et deux entrées différentes n'ont en pratique jamais la même empreinte.

La vraie difficulté, c'est d'avoir **une seule écriture par contenu** (idée de la RFC 8785, *JSON Canonicalization Scheme*) :
- les clés sont triées et il n'y a pas d'espaces (`canonical_json`) ;
- **les montants sont toujours des flottants**. Sinon `equal_stacks(10)` s'écrirait `[10,10,10]` et `equal_stacks(10.0)` s'écrirait `[10.0,10.0,10.0]`, ce qui donnerait deux empreintes pour la même partie ;
- les entrées du profil sont triées : le même profil écrit dans un autre ordre donne la même empreinte ;
- c'est le **contenu** du profil qui est haché, pas seulement son nom. Changer un facteur de 1,07 à 1,08 change l'empreinte.

Les tenseurs d'équité entrent dans l'empreinte par leur propre SHA-256 (`EquityTables.digest`, environ 0,2 s pour 3 × 169³ flottants), ce qui évite de hacher 115 Mo à chaque fois.

## 3. Écriture atomique

Une solution est d'abord écrite dans `<racine>/.tmp-<uuid>/`, puis ce dossier est **renommé** en `<racine>/<empreinte>/`. Sur un même disque, un renommage est tout-ou-rien. Si le PC s'arrête en plein batch, il reste au pire un dossier `.tmp-*`, que le store ignore, et jamais une solution à moitié écrite. La solution sera simplement recalculée.

L'index SQLite est mis à jour **après** le renommage. Les dossiers font foi : si l'index est perdu ou en retard, `rebuild_index()` le reconstruit en relisant les manifestes.

## 4. Format sur disque (version 1)

```
<racine>/index.sqlite                     une ligne par solution (listes)
<racine>/<empreinte>/manifest.json        métadonnées lisibles
<racine>/<empreinte>/arrays.npz           tableaux (compressés)
```

- **`manifest.json`** contient :
  - les versions du format, du schéma d'empreinte et du moteur ;
  - l'empreinte et la date ;
  - la config, l'**arbre complet**, le profil complet, les paramètres et l'empreinte des tenseurs ;
  - les itérations, la durée, l'exploitabilité (EV, gains, NashConv en %) et le statut publiable ;
  - le SHA-256 de `arrays.npz`, vérifié à chaque lecture.
- **`arrays.npz`** contient :
  - la stratégie de tous les nœuds de décision, concaténée dans l'ordre de l'arbre (actions × classes) ;
  - `reach`, `opponent_mass` et `ev` (nœuds × joueurs × classes, NaN compris) ;
  - `hand_mass`.

Une solution à 20bb pèse environ 2,7 Mo. Elle s'enregistre en 0,3 s et se relit en 0,06 s.

**Anciennes versions.** L'arbre est stocké avec la solution : la relecture ne dépend pas du constructeur d'arbre actuel. Une solution figée, écrite par une « version 0.0.0 », est gardée dans le dépôt (`tests/engine/library/data/legacy_store/`) pour vérifier qu'elle reste lisible. Si le format doit changer, on passe en format 2 et on garde la lecture du format 1.

## 5. À retenir

- Changer la version du moteur change **toutes** les empreintes et fait recalculer toute la bibliothèque. On ne la change que lorsque le calcul change.
- L'empreinte se calcule **avant** de résoudre (`fingerprint(tree, profile, params, equity_digest, engine_version)`). C'est ce qui permettra au batch (#25) de sauter une configuration déjà présente.
