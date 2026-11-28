"""EV loss, grade and session summary of the trainer (US4, D-008).

The EV loss of an action is ``max EV - EV(action)`` for the hand at the node
(conditional EVs of the solution, bb). Grades: best below 0.05bb, inaccuracy
from 0.05 to 0.25bb, mistake from 0.25bb. An action the equilibrium plays at
least ``mixed_frequency`` of the time is best: at equilibrium, every action
of a mixed strategy has the same EV (indifference), so any of them is right.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np

from engine.training.spots import Spot


class Grade(Enum):
    BEST = "best"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"


@dataclass(frozen=True)
class GradingThresholds:
    """D-008 thresholds, in bb of EV loss; ``mixed_frequency``: see D-017."""

    best: float = 0.05
    mistake: float = 0.25
    mixed_frequency: float = 0.01

    def __post_init__(self) -> None:
        if not 0 < self.best <= self.mistake:
            raise ValueError(f"need 0 < best <= mistake, got {self.best} and {self.mistake}")
        if not 0 <= self.mixed_frequency <= 1:
            raise ValueError(f"mixed_frequency must be in [0, 1], got {self.mixed_frequency}")


@dataclass(frozen=True)
class Answer:
    """The hero's choice at a spot, with its equilibrium frequency, EV loss and grade."""

    spot: Spot
    action: int
    frequency: float
    ev_loss: float
    grade: Grade
    best_action: int


def grade(spot: Spot, action: int, thresholds: GradingThresholds | None = None) -> Answer:
    """Grade the action of index ``action`` among the spot's actions."""
    thresholds = thresholds or GradingThresholds()
    n_actions = len(spot.strategy)
    if not 0 <= action < n_actions:
        raise ValueError(f"action must be in [0, {n_actions}), got {action}")
    evs = np.asarray(spot.action_ev, dtype=np.float64)
    best_action = int(evs.argmax())
    loss = max(0.0, float(evs[best_action] - evs[action]))
    frequency = float(spot.strategy[action])
    if frequency >= thresholds.mixed_frequency or loss < thresholds.best:
        result = Grade.BEST
    elif loss < thresholds.mistake:
        result = Grade.INACCURACY
    else:
        result = Grade.MISTAKE
    return Answer(spot, action, frequency, loss, result, best_action)


@dataclass(frozen=True)
class SessionSummary:
    """Score (share of best actions), EV loss and the answers to review."""

    count: int
    best: int
    inaccuracies: int
    mistakes: int
    total_loss: float
    errors: tuple[Answer, ...]

    @property
    def score(self) -> float:
        return self.best / self.count if self.count else 0.0

    @property
    def mean_loss(self) -> float:
        return self.total_loss / self.count if self.count else 0.0


def summarize(answers: Sequence[Answer]) -> SessionSummary:
    """Summary of a session (US4 scenario 4)."""
    grades = [answer.grade for answer in answers]
    return SessionSummary(
        count=len(answers),
        best=grades.count(Grade.BEST),
        inaccuracies=grades.count(Grade.INACCURACY),
        mistakes=grades.count(Grade.MISTAKE),
        total_loss=float(sum(answer.ev_loss for answer in answers)),
        errors=tuple(answer for answer in answers if answer.grade is not Grade.BEST),
    )
