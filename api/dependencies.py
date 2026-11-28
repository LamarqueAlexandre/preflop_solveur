"""Request dependencies: the store comes from the app, not a module global (principle VII)."""

from fastapi import Request

from engine.library import SolutionStore


def get_store(request: Request) -> SolutionStore:
    """Solution store of the application handling ``request``."""
    store: SolutionStore = request.app.state.store
    return store
