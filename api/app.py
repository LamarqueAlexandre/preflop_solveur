"""Application factory of the HTTP API."""

import os
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from api.dependencies import JobRuntime
from api.jobs import JobStore, SqliteJobStore
from api.routes import jobs, solutions, training, villain_strategies
from api.training import SqliteTrainingSessionStore, TrainingSessionStore
from api.villain_strategies import SqliteVillainStrategyStore, VillainStrategyStore
from api.worker import DirectoryEquity, EquitySource
from engine.library import FileSolutionStore, SolutionStore

DEFAULT_STORE = Path("data/solutions")
DEFAULT_JOBS = Path("data/jobs.sqlite3")
DEFAULT_EQUITY = Path("data/equity")
DEFAULT_VILLAINS = Path("data/villain_strategies.sqlite3")
DEFAULT_TRAINING = Path("data/training.sqlite3")
STORE_ENV = "PREFLOP_STORE"
JOBS_ENV = "PREFLOP_JOBS"
EQUITY_ENV = "PREFLOP_EQUITY"
WORKERS_ENV = "PREFLOP_JOB_WORKERS"
VILLAINS_ENV = "PREFLOP_VILLAINS"
TRAINING_ENV = "PREFLOP_TRAINING"


def create_app(
    store: SolutionStore,
    jobs_store: JobStore | None = None,
    equity: EquitySource | None = None,
    workers: int = 1,
    villains: VillainStrategyStore | None = None,
    training_sessions: TrainingSessionStore | None = None,
) -> FastAPI:
    """API serving ``store``; each app carries its own state, nothing is global.

    On-demand computations need ``jobs_store`` and ``equity``; without them the
    job routes answer 503, as the villain-strategy routes without
    ``villains`` and the training routes without ``training_sessions``.
    Workers run in a process pool owned by the app.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if jobs_store is None or equity is None:
            app.state.jobs = None
            yield
            return
        jobs_store.interrupt_unfinished()
        executor = ProcessPoolExecutor(max_workers=workers)
        app.state.jobs = JobRuntime(jobs_store, equity, executor)
        try:
            yield
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(
        title="Préflop Expresso 3-max",
        version="0.1.0",
        summary="Equilibrium strategies of the Expresso 3-max preflop game, in bb.",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.villains = villains
    app.state.training = training_sessions
    app.include_router(solutions.router)
    app.include_router(jobs.router)
    app.include_router(villain_strategies.router)
    app.include_router(training.router)
    return app


def app_from_env() -> FastAPI:
    """API configured by ``PREFLOP_STORE``, ``PREFLOP_JOBS``, ``PREFLOP_EQUITY``,
    ``PREFLOP_JOB_WORKERS``, ``PREFLOP_VILLAINS`` and ``PREFLOP_TRAINING``
    (defaults under ``data/``, one worker)."""
    return create_app(
        FileSolutionStore(Path(os.environ.get(STORE_ENV, DEFAULT_STORE))),
        SqliteJobStore(Path(os.environ.get(JOBS_ENV, DEFAULT_JOBS))),
        DirectoryEquity(Path(os.environ.get(EQUITY_ENV, DEFAULT_EQUITY))),
        workers=int(os.environ.get(WORKERS_ENV, "1")),
        villains=SqliteVillainStrategyStore(Path(os.environ.get(VILLAINS_ENV, DEFAULT_VILLAINS))),
        training_sessions=SqliteTrainingSessionStore(
            Path(os.environ.get(TRAINING_ENV, DEFAULT_TRAINING))
        ),
    )
