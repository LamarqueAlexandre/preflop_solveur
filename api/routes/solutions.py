"""Solution library: list, nearest depth, node reading (US1, US2)."""

import math
from typing import Annotated, Any, cast

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from numpy.typing import NDArray

from api.dependencies import get_store
from api.schemas import (
    ActionOut,
    DecisionNodeOut,
    ErrorOut,
    HandOut,
    NearestSolutionOut,
    NodeSummaryOut,
    PositionName,
    SolutionOut,
    TerminalNodeOut,
)
from engine.cards import CLASS_WEIGHTS, format_class, grid_position
from engine.library import (
    Solution,
    SolutionStore,
    SolutionSummary,
    nearest_solution,
    node_summary,
    terminal_view,
)

router = APIRouter(prefix="/solutions", tags=["solutions"])

Store = Annotated[SolutionStore, Depends(get_store)]
Fingerprint = Annotated[str, Path(pattern=r"^[0-9a-f]{64}$", description="SHA-256 fingerprint")]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut}}


def _solution_out(summary: SolutionSummary) -> SolutionOut:
    return SolutionOut(
        fingerprint=summary.fingerprint,
        depth=min(summary.stacks),
        stacks=summary.stacks,
        tranche=summary.tranche,
        profile_name=summary.profile_name,
        profile_version=summary.profile_version,
        engine_version=summary.engine_version,
        nash_conv_percent=summary.nash_conv_percent,
        iterations=summary.iterations,
        created_at=summary.created_at,
    )


def _floats(values: NDArray[np.float64]) -> list[float | None]:
    """JSON-safe list: NaN (undefined EV) becomes null."""
    return [float(v) if math.isfinite(v) else None for v in values.tolist()]


def _load(store: SolutionStore, fingerprint: str) -> Solution:
    """A publishable stored solution, or 404."""
    try:
        if not store.summary(fingerprint).publishable:
            raise KeyError(fingerprint)
        return store.load(fingerprint)
    except KeyError:
        raise HTTPException(404, f"solution {fingerprint} not found") from None


@router.get("", response_model=list[SolutionOut])
def list_solutions(store: Store) -> list[SolutionOut]:
    """Publishable solutions only (FR-010), by increasing depth."""
    summaries = store.list_solutions(publishable_only=True)
    return sorted((_solution_out(s) for s in summaries), key=lambda s: (s.depth, s.created_at))


@router.get("/nearest", response_model=NearestSolutionOut, responses=NOT_FOUND)
def nearest(
    store: Store, stack: Annotated[float, Query(gt=0, le=1000, description="Depth in bb")]
) -> NearestSolutionOut:
    """Solution at ``stack`` bb, or at the closest available depth (US1 scenario 4, D-018)."""
    found = nearest_solution(store.list_solutions(publishable_only=True), stack)
    if found is None:
        raise HTTPException(404, "the library has no publishable solution")
    return NearestSolutionOut(
        requested_stack=stack, exact=found.exact, solution=_solution_out(found.summary)
    )


@router.get(
    "/{fingerprint}/nodes/{node_id}",
    response_model=DecisionNodeOut | TerminalNodeOut,
    responses=NOT_FOUND,
)
def read_node(
    store: Store, fingerprint: Fingerprint, node_id: str
) -> DecisionNodeOut | TerminalNodeOut:
    """Decision node: strategy, EV and reach of each hand class, and summary (FR-021).

    Terminal: pot and mean EV of each player (US2 scenario 4).
    """
    solution = _load(store, fingerprint)
    if node_id not in solution.tree.nodes:
        raise HTTPException(404, f"node {node_id!r} not found")
    if solution.tree.node(node_id).is_terminal:
        view = terminal_view(solution, node_id)
        return TerminalNodeOut(
            fingerprint=fingerprint,
            node_id=node_id,
            kind=view.kind.value,
            reached=view.reached,
            pot=view.pot,
            contributions=view.contributions,
            folded=view.folded,
            ev=view.ev,
        )
    node = solution.node(node_id)
    summary = node_summary(solution, node_id)
    hands = [
        HandOut(
            hand=format_class(h),
            row=grid_position(h)[0],
            col=grid_position(h)[1],
            combos=int(CLASS_WEIGHTS[h]),
            strategy=[float(f) for f in node.strategy[:, h]],
            action_ev=_floats(node.action_ev[:, h]),
            ev=_floats(node.ev[:, h]),
            reach=[float(r) for r in node.reach[:, h]],
        )
        for h in range(node.strategy.shape[1])
    ]
    return DecisionNodeOut(
        fingerprint=fingerprint,
        node_id=node_id,
        actor=cast(PositionName, node.actor.name),
        actions=[
            ActionOut(
                kind=a.kind.value,
                amount=a.amount,
                label=a.token,
                child_id=child,
            )
            for a, child in zip(node.actions, solution.tree.node(node_id).children, strict=True)
        ],
        summary=NodeSummaryOut(
            reached=summary.reached,
            frequencies=list(summary.frequencies) if summary.frequencies is not None else None,
            range_fraction=summary.range_fraction,
            range_combos=summary.range_combos,
            pot=summary.pot,
        ),
        nash_conv_percent=solution.exploitability.percent,
        profile_name=solution.profile_name,
        profile_version=solution.profile_version,
        hands=hands,
    )
