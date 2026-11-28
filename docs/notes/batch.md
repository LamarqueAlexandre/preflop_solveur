# Batch de la bibliothèque : idempotent et reprenable

Note liée à FR-013 et US5 (issue #25). Code : `engine/library/batch.py`, commande `engine batch`.

## 1. Idempotence

Une opération est **idempotente** si la refaire ne change rien : f(f(x)) = f(x).

Pour chaque profondeur, le batch :
1. construit l'arbre et calcule l'**empreinte** ([stockage-solutions.md](stockage-solutions.md), D-016), **avant** de résoudre ;
2. si le store contient déjà cette empreinte, il passe à la suite ;
3. sinon, il résout, puis il enregistre.

Un batch relancé sans rien changer ne fait donc qu'un calcul d'empreinte par profondeur : le `digest` des tenseurs (environ 0,2 s, une seule fois) et quelques millisecondes par arbre. Le store n'est pas modifié : mêmes octets, mêmes dates de modification.

## 2. Reprise après interruption

La reprise se fait **à la profondeur**. Chaque solution est écrite de façon atomique (dossier temporaire puis renommage). Si le PC s'arrête pendant le calcul de 18bb :
- les profondeurs 3 à 17 sont déjà dans le store ;
- 18bb n'y est pas : au pire, il reste un dossier `.tmp-*`, ignoré ;
- à la relance, 3 à 17 sont « already stored » et le batch reprend à 18bb, depuis le début de sa résolution.

On perd au plus une résolution, environ 2 minutes à > 15bb. Sauvegarder régulièrement les regrets du DCFR pour reprendre en cours de résolution a été écarté : ce serait beaucoup plus complexe pour gagner au mieux 2 minutes.

**Exemple.** Batch sur {5, 12, 20}, interrompu pendant 20bb.

| Lancement | 5bb | 12bb | 20bb | Store |
|---|---|---|---|---|
| 1 (interrompu) | résolue | résolue | interrompue | 5, 12 |
| 2 | sautée | sautée | résolue | 5, 12, 20 |
| 3 | sautée | sautée | sautée | 5, 12, 20 |

## 3. Solutions non conformes

Une résolution qui n'atteint pas NashConv < 0,5 % dans la limite d'itérations (D-015) est **enregistrée avec le statut non publiable** (US5, scénario 3). Le batch la signale, et l'API ne listera que les solutions publiables (`list_solutions(publishable_only=True)`).

Même entrée, même empreinte : une relance ne la recalcule pas. Pour réessayer, on change un paramètre de convergence. Par exemple, `engine batch --stacks 22 --max-iterations 4000` donne une nouvelle empreinte, donc une nouvelle solution. L'ancienne reste dans le store, non publiée.

## 4. Erreurs

Une erreur (tenseurs absents ou partiels, profil illisible, stack invalide) arrête la commande avant tout calcul, avec le code de retour 1. Une erreur pendant le batch l'arrête aussi. Une fois le problème corrigé, il suffit de relancer : les profondeurs déjà calculées sont sautées.

## 5. Commandes

```bash
uv run engine batch                          # grille 3–25bb, store data/solutions/
uv run engine batch --stacks 5,12,20         # quelques profondeurs
uv run engine batch --stacks 3-8 --store mon_store --target 0.05
```

Sur un poste où le contrôle d'application bloque l'exécutable `engine` créé par uv, utiliser `uv run python -m engine.cli batch …`.

Essai réel (vrais tenseurs, 5 et 12bb) : 38 s pour les deux profondeurs (100 itérations chacune, NashConv de 0,002 % et 0,096 %). Une relance ne recalcule rien.
