"""Application factory of the HTTP API."""

import os
from pathlib import Path

from fastapi import FastAPI

from api.routes import solutions
from engine.library import FileSolutionStore, SolutionStore

DEFAULT_STORE = Path("data/solutions")
STORE_ENV = "PREFLOP_STORE"


def create_app(store: SolutionStore) -> FastAPI:
    """API serving ``store``; each app carries its own store, nothing is global."""
    app = FastAPI(
        title="Préflop Expresso 3-max",
        version="0.1.0",
        summary="Equilibrium strategies of the Expresso 3-max preflop game, in bb.",
    )
    app.state.store = store
    app.include_router(solutions.router)
    return app


def app_from_env() -> FastAPI:
    """API on the file store named by ``PREFLOP_STORE`` (default ``data/solutions``)."""
    return create_app(FileSolutionStore(Path(os.environ.get(STORE_ENV, DEFAULT_STORE))))
