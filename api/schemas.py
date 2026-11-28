"""Response models of the HTTP API. Amounts in bb, EV per D-007."""

from typing import Literal

from pydantic import BaseModel, Field

PositionName = Literal["BTN", "SB", "BB"]
ActionKindName = Literal["F", "C", "X", "R", "A"]
TerminalKindName = Literal["fold", "showdown", "flop"]


class SolutionOut(BaseModel):
    """One solution of the library."""

    fingerprint: str
    depth: float = Field(description="Smallest stack of the configuration, in bb")
    stacks: tuple[float, float, float] = Field(description="Stacks of BTN, SB, BB, in bb")
    tranche: str
    profile_name: str
    profile_version: str
    engine_version: str
    nash_conv_percent: float = Field(description="Exploitability, % of the 1.5bb starting pot")
    iterations: int
    created_at: str


class NearestSolutionOut(BaseModel):
    """Solution at the requested depth, or at the closest available one (US1 scenario 4)."""

    requested_stack: float
    exact: bool
    solution: SolutionOut


class ActionOut(BaseModel):
    kind: ActionKindName
    amount: float = Field(description="Actor's total contribution after the action, in bb")
    label: str
    child_id: str


class HandOut(BaseModel):
    """One of the 169 hand classes at a decision node."""

    hand: str = Field(description='Class notation, e.g. "AKs"')
    row: int
    col: int
    combos: int
    strategy: list[float] = Field(description="Frequency of each action, in action order")
    action_ev: list[float | None] = Field(description="Actor's EV of each action, in bb")
    ev: list[float | None] = Field(description="EV of BTN, SB, BB holding this hand, in bb")
    reach: list[float] = Field(description="Reach of BTN, SB, BB holding this hand")


class NodeSummaryOut(BaseModel):
    reached: bool
    frequencies: list[float] | None = Field(description="Range-wide frequency of each action")
    range_fraction: tuple[float, float, float]
    range_combos: tuple[float, float, float]
    pot: float


class DecisionNodeOut(BaseModel):
    type: Literal["decision"] = "decision"
    fingerprint: str
    node_id: str
    actor: PositionName
    actions: list[ActionOut]
    summary: NodeSummaryOut
    nash_conv_percent: float
    profile_name: str
    profile_version: str
    hands: list[HandOut]


class TerminalNodeOut(BaseModel):
    type: Literal["terminal"] = "terminal"
    fingerprint: str
    node_id: str
    kind: TerminalKindName
    reached: bool
    pot: float
    contributions: tuple[float, float, float]
    folded: tuple[bool, bool, bool]
    ev: tuple[float | None, float | None, float | None]


class ErrorOut(BaseModel):
    detail: str


FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
JobStatusName = Literal["pending", "running", "done", "failed"]
JobKindName = Literal["best_response"]


class BestResponseIn(BaseModel):
    """Best response of ``hero`` against villains locked at some nodes (FR-014, FR-015)."""

    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN, description="Solution fingerprint")
    hero: PositionName
    locks: dict[str, list[list[float]]] = Field(
        min_length=1,
        description=(
            "Villain strategy at each locked node: one row per action (node action order), "
            "each row giving the frequency of every hand class (node hand order)"
        ),
    )


class HandGainOut(BaseModel):
    hand: str
    row: int
    col: int
    combos: int
    gain: float | None = Field(description="EV gained with this hand, bb per hand dealt")


class HeroHandOut(BaseModel):
    hand: str
    equilibrium: list[float] = Field(description="Equilibrium frequency of each action")
    best: list[float] = Field(description="Best-response frequency of each action")
    frequency_gap: list[float] = Field(description="best - equilibrium, for each action")
    ev_gain: float | None = Field(
        description="EV gained from this node on, hero here with this hand, in bb"
    )


class HeroNodeOut(BaseModel):
    """Comparison with equilibrium at one decision node of the hero (FR-016)."""

    node_id: str
    actions: list[ActionOut]
    hands: list[HeroHandOut]


class BestResponseOut(BaseModel):
    """Best response and EV gained over equilibrium, in bb per hand dealt (D-006)."""

    fingerprint: str
    hero: PositionName
    locked_nodes: list[str]
    value: float = Field(description="Hero EV with the best response")
    equilibrium_ev: float = Field(description="Hero EV with equilibrium, same villains")
    gain: float = Field(description="value - equilibrium_ev")
    hands: list[HandGainOut]
    nodes: list[HeroNodeOut]
    limitations: list[str] = Field(description="Limits of the computation (FR-018)")


class JobOut(BaseModel):
    """State of an on-demand job; ``result`` once ``done``, ``error`` once ``failed``."""

    id: str
    kind: JobKindName
    status: JobStatusName
    created_at: str
    updated_at: str
    error: str | None
    result: BestResponseOut | None
