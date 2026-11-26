# Installer le projet sur un nouveau PC Windows

Cette procédure prépare un poste pour travailler sur le projet avec VS Code et l'extension Claude Code.

Tout ce qui est configuré **côté GitHub** est déjà en place et ne se refait pas : issues, milestones, labels, protection de `main` et `dev`, suppression automatique des branches mergées. Seul le **poste** est à configurer.

---

## 1. Installer les outils

Ouvre **PowerShell** et lance, une ligne à la fois :

```powershell
winget install --id Git.Git
winget install --id Microsoft.VisualStudioCode
winget install --id GitHub.cli
winget install --id astral-sh.uv
```

- Inutile d'installer Python : uv télécharge tout seul la bonne version (3.12) à l'étape 5.
- Si un outil est déjà installé, saute sa ligne.

**Ferme ensuite PowerShell et rouvre-le**, pour que les nouvelles commandes soient reconnues.

## 2. Configurer ton identité Git

```powershell
git config --global user.name "Alexandre Lamarque"
git config --global user.email "<l'adresse e-mail de ton compte GitHub>"
```

Avec cette adresse, tes commits sont rattachés à ton compte GitHub.

## 3. Connecter le PC à GitHub (clé SSH et `gh`)

```powershell
gh auth login
```

Réponds aux questions dans cet ordre :

1. **Where do you use GitHub?** → `GitHub.com`
2. **Preferred protocol for Git operations?** → `SSH`
3. **Generate a new SSH key to add to your GitHub account?** → `Yes`. Une passphrase est facultative : Entrée pour aucune. Le titre peut être `PC maison`.
4. **How would you like to authenticate GitHub CLI?** → `Login with a web browser`
5. ⚠️ **Le terminal affiche un code** du type `ABCD-1234`, juste avant d'ouvrir le navigateur. **Note-le** : c'est ce code que la page GitHub demande. Il n'arrive pas par mail. S'il a expiré (au bout d'environ 15 minutes), relance `gh auth login`.

Pour vérifier :

```powershell
gh auth status
ssh -T git@github.com
```

- La première commande doit afficher `✓ Logged in to github.com account LamarqueAlexandre`.
- Pour la seconde, réponds `yes` si on te demande de confirmer la connexion. Elle doit afficher `Hi LamarqueAlexandre! You've successfully authenticated`.

## 4. Récupérer le projet

Place-toi dans le dossier où tu veux ranger le projet, puis :

```powershell
git clone git@github.com:LamarqueAlexandre/preflop_solveur.git
cd preflop_solveur
git checkout dev
```

## 5. Installer les dépendances et vérifier

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run mypy engine/
```

Les trois vérifications doivent être vertes.

## 6. VS Code et l'extension Claude

1. Ouvre VS Code, puis **File → Open Folder** → le dossier `preflop_solveur`.
2. Installe l'extension **Claude Code** depuis le panneau Extensions (Ctrl+Shift+X), si elle n'y est pas déjà.
3. Connecte-toi avec ton compte Claude quand l'extension le demande.
4. ⚠️ **Redémarre complètement VS Code** après les installations de l'étape 1. Sinon Claude risque de ne pas trouver `gh`.
5. Pour tester, demande à Claude : « vérifie `gh auth status` et `gh issue list` ».

---

## Ce qui ne suit pas d'un PC à l'autre

| Élément | Où il vit | Conséquence |
|---|---|---|
| Règles du projet (`.claude/CLAUDE.md`, `docs/`) | dans le dépôt | ✅ récupérées avec le clone |
| Conversations avec Claude | sur chaque PC | ❌ Claude repart de zéro. Le contexte vit dans les issues, les PR et `docs/`, donc rien d'important n'est perdu. |
| Mémoire automatique de Claude | sur chaque PC | ❌ les habitudes importantes sont inscrites dans `.claude/CLAUDE.md` |
| Permissions accordées à Claude (`.claude/settings.local.json`) | volontairement hors git | ❌ tu les réaccordes au fil des demandes |

## La règle d'or quand on travaille sur deux PC

- **Avant de partir** d'un PC : tout est commité et poussé, et `git status` affiche « nothing to commit ».
- **En arrivant** sur l'autre PC :

  ```powershell
  git checkout dev
  git pull
  ```

- **Pour reprendre une issue en cours** commencée sur l'autre PC :

  ```powershell
  git fetch
  git checkout issue-<n>-<nom>
  ```

Si tu oublies de pousser avant de partir, le travail reste bloqué sur l'autre PC. Ce n'est pas grave, mais il faudra y retourner.
