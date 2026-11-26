# Solveur préflop Expresso 3-max

Solveur préflop à 3 joueurs pour le format Expresso (stacks de 3 à 25bb).
Voir [docs/spec.md](docs/spec.md) et [docs/plan.md](docs/plan.md).

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/). Installation complète d'un nouveau poste (Git, GitHub CLI, clé SSH, VS Code, Claude Code) : [docs/installation-poste.md](docs/installation-poste.md).

```bash
uv sync
```

## Commandes

```bash
uv run pytest                # tests
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy engine/          # typage du moteur
```

## Arborescence

- `engine/` : moteur Python autonome, sans dépendance web
- `api/` : API FastAPI, couche fine sans logique de poker
- `tests/` : tests du moteur et de l'API
- `benchmarks/` : benchmarks reproductibles
- `data/` : tenseurs d'équité et bibliothèque de solutions (hors git, régénérables)
- `docs/` : constitution, spec, plan, décisions, notes
