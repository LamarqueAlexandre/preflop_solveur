"""Training sessions: create, next spot, answer, summary (US4, FR-025, D-021).

Spots are drawn by ``engine.training.draw_spots`` at creation and graded by
``engine.training.grade``: the API only stores and formats them.
"""

import math
import secrets
from typing import Annotated, Any, cast

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Path
from numpy.typing import NDArray

from api.dependencies import get_store, get_training
from api.routes.solutions import NOT_FOUND
from api.schemas import (
    SESSION_ID_PATTERN,
    AnswerIn,
    AnswerOut,
    AnswerResultOut,
    ErrorOut,
    HistoryActionOut,
    PositionName,
    SpotActionOut,
    SpotOut,
    TrainingSessionIn,
    TrainingSessionOut,
    TrainingSummaryOut,
)
from api.training import AnswerConflictError, TrainingSession, TrainingSessionStore
from engine.game import Action, Position
from engine.library import SolutionStore
from engine.training import (
    Answer,
    Grade,
    Spot,
    SpotFilters,
    SpotType,
    draw_spots,
    grade,
    summarize,
)

router = APIRouter(prefix="/training/sessions", tags=["training"])

Store = Annotated[SolutionStore, Depends(get_store)]
Sessions = Annotated[TrainingSessionStore, Depends(get_training)]
SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN, description="Session identifier")]
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorOut}}


def _floats(values: NDArray[np.float64]) -> list[float | None]:
    """JSON-safe list: NaN (undefined EV) becomes null."""
    return [float(v) if math.isfinite(v) else None for v in values.tolist()]


def _session_out(session: TrainingSession) -> TrainingSessionOut:
    filters = session.filters
    return TrainingSessionOut(
        id=session.id,
        positions=[cast(PositionName, p.name) for p in sorted(filters.positions)],
        types=[t.value for t in SpotType if t in filters.types],
        min_stack=filters.min_stack,
        max_stack=filters.max_stack,
        seed=session.seed,
        count=len(session.spots),
        answered=len(session.answers),
        finished=session.finished,
        created_at=session.created_at,
    )


def _action_out(action: Action) -> SpotActionOut:
    return SpotActionOut(kind=action.kind.value, amount=action.amount, label=action.token)


def _spot_out(index: int, spot: Spot) -> SpotOut:
    return SpotOut(
        index=index,
        fingerprint=spot.fingerprint,
        stack=spot.stack,
        node_id=spot.node_id,
        hero=cast(PositionName, spot.hero.name),
        spot_type=spot.spot_type.value,
        history=[
            HistoryActionOut(actor=cast(PositionName, player.name), **_action_out(a).model_dump())
            for player, a in spot.history
        ],
        hand=spot.hand,
        cards=spot.cards_text or None,
        actions=[_action_out(action) for action in spot.actions],
    )


def _answer_out(index: int, answer: Answer) -> AnswerOut:
    spot = answer.spot
    return AnswerOut(
        spot=_spot_out(index, spot),
        action=spot.actions[answer.action].token,
        best_action=spot.actions[answer.best_action].token,
        grade=answer.grade.value,
        ev_loss=answer.ev_loss,
        frequency=answer.frequency,
        strategy=spot.strategy.tolist(),
        action_ev=_floats(spot.action_ev),
    )


def _answers(session: TrainingSession) -> list[Answer]:
    return [
        grade(spot, action) for spot, action in zip(session.spots, session.answers, strict=False)
    ]


def _found(sessions: TrainingSessionStore, session_id: str) -> TrainingSession:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(404, f"training session {session_id} not found")
    return session


@router.post(
    "",
    status_code=201,
    response_model=TrainingSessionOut,
    responses={422: {"model": ErrorOut}},
)
def create_session(
    request: TrainingSessionIn, store: Store, sessions: Sessions
) -> TrainingSessionOut:
    """Draw every spot of the session now; 422 if no spot matches the filters."""
    try:
        filters = SpotFilters(
            positions=frozenset(Position[name] for name in request.positions),
            types=frozenset(SpotType(name) for name in request.types),
            min_stack=request.min_stack,
            max_stack=request.max_stack,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    summaries = [
        summary
        for summary in store.list_solutions(publishable_only=True)
        if filters.accepts_stack(min(summary.stacks))
    ]
    solutions = {summary.fingerprint: store.load(summary.fingerprint) for summary in summaries}
    seed = request.seed if request.seed is not None else secrets.randbelow(2**63)
    try:
        spots = draw_spots(solutions, filters, request.count, seed)
    except ValueError as error:  # no solution or no spot matches the filters
        raise HTTPException(422, str(error)) from None
    return _session_out(sessions.create(filters, seed, spots))


@router.get("/{session_id}", response_model=TrainingSessionOut, responses=NOT_FOUND)
def read_session(session_id: SessionId, sessions: Sessions) -> TrainingSessionOut:
    return _session_out(_found(sessions, session_id))


@router.get("/{session_id}/spot", response_model=SpotOut, responses={**NOT_FOUND, **CONFLICT})
def current_spot(session_id: SessionId, sessions: Sessions) -> SpotOut:
    """Next unanswered spot, without its answer key; 409 once the session is over."""
    session = _found(sessions, session_id)
    if session.finished:
        raise HTTPException(409, "the session is over")
    index = len(session.answers)
    return _spot_out(index, session.spots[index])


@router.post(
    "/{session_id}/answers",
    response_model=AnswerResultOut,
    responses={**NOT_FOUND, **CONFLICT, 422: {"model": ErrorOut}},
)
def answer_spot(session_id: SessionId, request: AnswerIn, sessions: Sessions) -> AnswerResultOut:
    """Answer the current spot by action label; feedback with the answer key."""
    session = _found(sessions, session_id)
    if session.finished:
        raise HTTPException(409, "the session is over")
    index = len(session.answers)
    spot = session.spots[index]
    labels = [action.token for action in spot.actions]
    if request.action not in labels:
        raise HTTPException(422, f"unknown action {request.action!r}, expected one of {labels}")
    action = labels.index(request.action)
    try:
        updated = sessions.answer(session_id, index, action)
    except AnswerConflictError as error:
        raise HTTPException(409, str(error)) from None
    if updated is None:
        raise HTTPException(404, f"training session {session_id} not found")
    return AnswerResultOut(
        **_answer_out(index, grade(spot, action)).model_dump(),
        answered=len(updated.answers),
        finished=updated.finished,
    )


@router.get("/{session_id}/summary", response_model=TrainingSummaryOut, responses=NOT_FOUND)
def session_summary(session_id: SessionId, sessions: Sessions) -> TrainingSummaryOut:
    """Score, EV loss and errors over the answers given so far."""
    session = _found(sessions, session_id)
    answers = _answers(session)
    summary = summarize(answers)
    return TrainingSummaryOut(
        count=len(session.spots),
        answered=summary.count,
        best=summary.best,
        inaccuracies=summary.inaccuracies,
        mistakes=summary.mistakes,
        score=summary.score,
        total_loss=summary.total_loss,
        mean_loss=summary.mean_loss,
        errors=[
            _answer_out(index, answer)
            for index, answer in enumerate(answers)
            if answer.grade is not Grade.BEST
        ],
    )
