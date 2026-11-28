"""Request dependencies: state comes from the app, not a module global (principle VII)."""

from concurrent.futures import Executor
from dataclasses import dataclass

from fastapi import HTTPException, Request

from api.jobs import JobStore
from api.villain_strategies import VillainStrategyStore
from api.worker import EquitySource
from engine.library import SolutionStore


def get_store(request: Request) -> SolutionStore:
    """Solution store of the application handling ``request``."""
    store: SolutionStore = request.app.state.store
    return store


@dataclass(frozen=True)
class JobRuntime:
    """What on-demand jobs need: their store, the equity tables and the executor."""

    store: JobStore
    equity: EquitySource
    executor: Executor


def get_jobs(request: Request) -> JobRuntime:
    """Job runtime of the application; 503 when on-demand computations are off."""
    runtime: JobRuntime | None = getattr(request.app.state, "jobs", None)
    if runtime is None:
        raise HTTPException(503, "on-demand computations are not configured")
    return runtime


def get_villains(request: Request) -> VillainStrategyStore:
    """Saved villain strategies of the application; 503 when not configured."""
    villains: VillainStrategyStore | None = getattr(request.app.state, "villains", None)
    if villains is None:
        raise HTTPException(503, "saved villain strategies are not configured")
    return villains
