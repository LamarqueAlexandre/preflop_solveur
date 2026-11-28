"""Saved villain strategies: create, list, read, replace, delete (FR-017, D-020)."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from api.dependencies import get_villains
from api.routes.solutions import NOT_FOUND
from api.schemas import (
    ErrorOut,
    InvalidStrategyOut,
    PositionName,
    VillainStrategyIn,
    VillainStrategyOut,
    VillainStrategySummaryOut,
)
from api.villain_strategies import (
    DuplicateNameError,
    VillainStrategy,
    VillainStrategyData,
    VillainStrategyStore,
)
from engine.best_response import StrategyError, validate_saved

router = APIRouter(prefix="/villain-strategies", tags=["villain strategies"])

Villains = Annotated[VillainStrategyStore, Depends(get_villains)]
StrategyId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="Strategy identifier")]
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorOut},
    422: {"model": InvalidStrategyOut},
}


def _summary(strategy: VillainStrategy) -> VillainStrategySummaryOut:
    data = strategy.data
    return VillainStrategySummaryOut(
        id=strategy.id,
        name=data.name,
        description=data.description,
        actor=cast(PositionName, data.actor),
        actions=data.actions,
        fingerprint=data.fingerprint,
        node_id=data.node_id,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


def _full(strategy: VillainStrategy) -> VillainStrategyOut:
    return VillainStrategyOut(
        **_summary(strategy).model_dump(), frequencies=strategy.data.frequencies
    )


def _checked(request: VillainStrategyIn) -> VillainStrategyData:
    """Data validated by the engine; 422 naming the faulty hands otherwise."""
    try:
        frequencies = validate_saved(request.actions, request.frequencies)
    except StrategyError as error:
        raise HTTPException(422, {"message": str(error), "hands": list(error.hands)}) from None
    except ValueError as error:
        raise HTTPException(422, {"message": str(error), "hands": []}) from None
    return VillainStrategyData(
        name=request.name,
        description=request.description,
        actor=request.actor,
        actions=list(request.actions),
        frequencies=frequencies.tolist(),
        fingerprint=request.fingerprint,
        node_id=request.node_id,
    )


def _not_found(strategy_id: str) -> HTTPException:
    return HTTPException(404, f"villain strategy {strategy_id} not found")


@router.post("", status_code=201, response_model=VillainStrategyOut, responses=WRITE_ERRORS)
def create_strategy(request: VillainStrategyIn, villains: Villains) -> VillainStrategyOut:
    """Save a named villain strategy; 409 if the name is taken."""
    try:
        return _full(villains.create(_checked(request)))
    except DuplicateNameError as error:
        raise HTTPException(409, str(error)) from None


@router.get("", response_model=list[VillainStrategySummaryOut])
def list_strategies(villains: Villains) -> list[VillainStrategySummaryOut]:
    """Every saved strategy by name, without frequencies."""
    return [_summary(strategy) for strategy in villains.list()]


@router.get("/{strategy_id}", response_model=VillainStrategyOut, responses=NOT_FOUND)
def read_strategy(strategy_id: StrategyId, villains: Villains) -> VillainStrategyOut:
    strategy = villains.get(strategy_id)
    if strategy is None:
        raise _not_found(strategy_id)
    return _full(strategy)


@router.put(
    "/{strategy_id}",
    response_model=VillainStrategyOut,
    responses={**NOT_FOUND, **WRITE_ERRORS},
)
def replace_strategy(
    strategy_id: StrategyId, request: VillainStrategyIn, villains: Villains
) -> VillainStrategyOut:
    """Replace a saved strategy (same checks as creation)."""
    try:
        strategy = villains.update(strategy_id, _checked(request))
    except DuplicateNameError as error:
        raise HTTPException(409, str(error)) from None
    if strategy is None:
        raise _not_found(strategy_id)
    return _full(strategy)


@router.delete("/{strategy_id}", status_code=204, responses=NOT_FOUND)
def delete_strategy(strategy_id: StrategyId, villains: Villains) -> Response:
    if not villains.delete(strategy_id):
        raise _not_found(strategy_id)
    return Response(status_code=204)
