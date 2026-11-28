"""On-demand computations: best response (US3, FR-014 to FR-016) and job state."""

from collections.abc import Callable
from concurrent.futures import Future
from typing import Annotated, cast

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Path

from api.dependencies import JobRuntime, get_jobs, get_store
from api.jobs import INTERRUPTED, Job, JobStore
from api.routes.solutions import NOT_FOUND, load_publishable
from api.schemas import BestResponseIn, BestResponseOut, JobKindName, JobOut
from api.worker import BEST_RESPONSE, best_response_params, run_best_response
from engine.best_response import validate_locks
from engine.game.tree import Position
from engine.library import SolutionStore

router = APIRouter(tags=["jobs"])

Store = Annotated[SolutionStore, Depends(get_store)]
Runtime = Annotated[JobRuntime, Depends(get_jobs)]
JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="Job identifier")]


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        kind=cast(JobKindName, job.kind),
        status=job.status.value,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        result=BestResponseOut.model_validate(job.result) if job.result is not None else None,
    )


def _on_worker_exit(jobs: JobStore, job_id: str) -> Callable[[Future[None]], None]:
    """Fail the job if its worker never ran it (cancelled) or died (broken pool)."""

    def callback(future: Future[None]) -> None:
        if future.cancelled():
            jobs.fail(job_id, INTERRUPTED)
        elif (error := future.exception()) is not None:
            jobs.fail(job_id, f"worker failure: {type(error).__name__}: {error}")

    return callback


@router.post("/best-response", status_code=202, response_model=JobOut, responses=NOT_FOUND)
def start_best_response(request: BestResponseIn, store: Store, runtime: Runtime) -> JobOut:
    """Start the best response of ``hero`` against the locked villains; returns the job.

    The locks are checked now (422 if invalid); the computation runs in a worker.
    """
    solution = load_publishable(store, request.fingerprint)
    hero = Position[request.hero]
    try:
        locks = {
            node_id: np.asarray(rows, dtype=np.float64) for node_id, rows in request.locks.items()
        }
        validate_locks(solution.tree, locks, hero, len(solution.hand_mass))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    job = runtime.store.create(
        BEST_RESPONSE, best_response_params(request.fingerprint, request.hero, request.locks)
    )
    future = runtime.executor.submit(
        run_best_response, runtime.store, store, runtime.equity, job.id
    )
    future.add_done_callback(_on_worker_exit(runtime.store, job.id))
    return _job_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut, responses=NOT_FOUND)
def read_job(job_id: JobId, runtime: Runtime) -> JobOut:
    """State of a job, with its result once done or its error once failed."""
    job = runtime.store.get(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found")
    return _job_out(job)
