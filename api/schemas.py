"""Response models of the HTTP API. Amounts in bb, EV per D-007."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

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


class VillainStrategyIn(BaseModel):
    """A named strategy of one node, reusable on nodes with the same actions (FR-017, D-020)."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: str = Field(default="", max_length=1000)
    actor: PositionName = Field(description="Villain the strategy was built for")
    actions: list[str] = Field(description='Action labels, e.g. ["F", "C", "R2.0", "A"]')
    frequencies: list[list[float]] = Field(
        description="One row per action (same order), each giving the 169 hand classes "
        "in engine order (as in GET /solutions/{fingerprint}/nodes/{node_id})"
    )
    fingerprint: str | None = Field(
        default=None, pattern=FINGERPRINT_PATTERN, description="Solution it was built on"
    )
    node_id: str | None = Field(default=None, description="Node it was built on")


class VillainStrategySummaryOut(BaseModel):
    """A saved strategy without its frequencies (list view)."""

    id: str
    name: str
    description: str
    actor: PositionName
    actions: list[str]
    fingerprint: str | None
    node_id: str | None
    created_at: str
    updated_at: str


class VillainStrategyOut(VillainStrategySummaryOut):
    frequencies: list[list[float]]


class InvalidStrategyDetail(BaseModel):
    message: str
    hands: list[str] = Field(description="Hand classes whose frequencies are invalid")


class InvalidStrategyOut(BaseModel):
    detail: InvalidStrategyDetail


class JobOut(BaseModel):
    """State of an on-demand job; ``result`` once ``done``, ``error`` once ``failed``."""

    id: str
    kind: JobKindName
    status: JobStatusName
    created_at: str
    updated_at: str
    error: str | None
    result: BestResponseOut | None


SpotTypeName = Literal["open", "vs_limp", "vs_raise", "vs_3bet", "vs_4bet"]
GradeName = Literal["best", "inaccuracy", "mistake"]
SESSION_ID_PATTERN = r"^[0-9a-f]{32}$"


class TrainingSessionIn(BaseModel):
    """Filters of a training session (US4 scenario 1); an empty list means all."""

    positions: list[PositionName] = Field(default=[], description="Hero positions")
    types: list[SpotTypeName] = Field(default=[], description="Spot types")
    min_stack: float | None = Field(default=None, gt=0, description="Smallest depth, in bb")
    max_stack: float | None = Field(default=None, gt=0, description="Largest depth, in bb")
    count: int = Field(default=20, ge=1, le=100, description="Number of spots")
    seed: int | None = Field(
        default=None, ge=0, lt=2**63, description="Draw seed; random (and returned) if omitted"
    )


class TrainingSessionOut(BaseModel):
    id: str
    positions: list[PositionName]
    types: list[SpotTypeName]
    min_stack: float | None
    max_stack: float | None
    seed: int
    count: int
    answered: int
    finished: bool
    created_at: str


class SpotActionOut(BaseModel):
    kind: ActionKindName
    amount: float = Field(description="Actor's total contribution after the action, in bb")
    label: str


class HistoryActionOut(SpotActionOut):
    actor: PositionName


class SpotOut(BaseModel):
    """A question of the trainer, without its answer key."""

    index: int = Field(description="Position of the spot in the session, from 0")
    fingerprint: str
    stack: float = Field(description="Depth, in bb")
    node_id: str
    hero: PositionName
    spot_type: SpotTypeName
    history: list[HistoryActionOut] = Field(description="Actions before the spot, in order")
    hand: str = Field(description='Class notation, e.g. "AKs"')
    cards: str | None = Field(description='Combo dealt, highest rank first, e.g. "AhKh"')
    actions: list[SpotActionOut]


class AnswerIn(BaseModel):
    action: str = Field(description='Label of the chosen action, e.g. "R2.0"')


class AnswerOut(BaseModel):
    """Feedback on an answer (US4 scenarios 2 and 3)."""

    spot: SpotOut
    action: str = Field(description="Label of the chosen action")
    best_action: str = Field(description="Label of the action with the highest EV")
    grade: GradeName
    ev_loss: float = Field(description="EV of the best action minus EV of the choice, in bb")
    frequency: float = Field(description="Equilibrium frequency of the chosen action")
    strategy: list[float] = Field(description="Equilibrium frequency of each action")
    action_ev: list[float | None] = Field(description="Hero's EV of each action, in bb")


class AnswerResultOut(AnswerOut):
    answered: int
    finished: bool


class TrainingSummaryOut(BaseModel):
    """Session summary over the answers given so far (US4 scenario 4)."""

    count: int = Field(description="Spots in the session")
    answered: int
    best: int
    inaccuracies: int
    mistakes: int
    score: float = Field(description="Share of answers graded best")
    total_loss: float = Field(description="Total EV loss, in bb")
    mean_loss: float = Field(description="Mean EV loss per answer, in bb")
    errors: list[AnswerOut] = Field(description="Answers not graded best, in session order")
