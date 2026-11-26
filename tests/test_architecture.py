"""Architecture guard: the engine never depends on the web layer (constitution, principle IV)."""

import ast
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1] / "engine"

FORBIDDEN_TOP_LEVEL = frozenset({"api", "fastapi", "starlette", "uvicorn", "pydantic", "httpx"})


def forbidden_imports(source: str) -> list[str]:
    """Return the forbidden top-level modules imported by ``source``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        found.extend(n for n in names if n.split(".")[0] in FORBIDDEN_TOP_LEVEL)
    return found


@pytest.mark.parametrize(
    "source",
    [
        "import fastapi",
        "import api.routes",
        "from api import app",
        "from pydantic import BaseModel",
        "def f():\n    import uvicorn\n",
    ],
)
def test_checker_detects_forbidden_imports(source: str) -> None:
    assert forbidden_imports(source)


@pytest.mark.parametrize(
    "source",
    [
        "import numpy as np",
        "from engine.cards import Card",
        "from . import api",
        "import apiary",
    ],
)
def test_checker_accepts_allowed_imports(source: str) -> None:
    assert forbidden_imports(source) == []


def test_engine_has_no_web_dependency() -> None:
    files = sorted(ENGINE_DIR.rglob("*.py"))
    assert files, "engine/ contains no Python file"
    violations = {
        str(path.relative_to(ENGINE_DIR)): bad
        for path in files
        if (bad := forbidden_imports(path.read_text(encoding="utf-8")))
    }
    assert violations == {}
