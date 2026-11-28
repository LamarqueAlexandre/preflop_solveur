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
