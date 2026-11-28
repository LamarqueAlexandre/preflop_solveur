"""Training spots drawn from the library with their real frequency (US4, D-009).

A spot is a (solution, decision node, hand) of the player to act, the hero.
Each (node, hand) is drawn with weight ``reach_hero(n, h) * m_hero(n, h)``:
the probability that the hero gets there with h, times the weight of the
opponent hands still possible (their actions and card removal). Hands that
never reach a node are never asked about. The depth is drawn uniformly among
the solutions passing the filters. See docs/notes/entrainement.md.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from numpy.typing import NDArray

from engine.cards import COMBOS, N_CLASSES, card_rank, combos_of_class, format_card, format_class
from engine.game.tree import ROOT_ID, Action, GameTree, Node, Position
from engine.library.solution import Solution


class SpotType(Enum):
    """What the hero faces at a node."""

    OPEN = "open"  # nobody in before the hero
    VS_LIMP = "vs_limp"  # one or more limps, no raise (big blind check option included)
    VS_RAISE = "vs_raise"  # one raise (open or isolation)
    VS_3BET = "vs_3bet"
    VS_4BET = "vs_4bet"


_BY_LEVEL = {1: SpotType.VS_RAISE, 2: SpotType.VS_3BET}


def spot_type(tree: GameTree, node: Node) -> SpotType:
    """Type of a decision node, from its raise level and the limps before it."""
    if node.actor is None:
        raise ValueError(f"node {node.id!r} is a terminal: it is not a spot")
    if node.raise_level >= 3:
        return SpotType.VS_4BET
    if node.raise_level > 0:
        return _BY_LEVEL[node.raise_level]
    big_blind = tree.config.big_blind
    limped = any(
        player is not Position.BB
        and not node.folded[player]
        and node.contributions[player] >= big_blind
        for player in Position
    )
    return SpotType.VS_LIMP if limped else SpotType.OPEN


def _frozen[T](values: Iterable[T]) -> frozenset[T]:
    return frozenset(values)


@dataclass(frozen=True)
class SpotFilters:
    """Hero positions, spot types and stack range (bounds included); empty means all."""

    positions: frozenset[Position] = frozenset()
    types: frozenset[SpotType] = frozenset()
    min_stack: float | None = None
    max_stack: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "positions", _frozen(self.positions))
        object.__setattr__(self, "types", _frozen(self.types))
        for bound in (self.min_stack, self.max_stack):
            if bound is not None and not bound > 0:
                raise ValueError(f"stack bounds must be positive, got {bound}")
        if (
            self.min_stack is not None
            and self.max_stack is not None
            and self.min_stack > self.max_stack
        ):
            raise ValueError(f"empty stack range {self.min_stack}-{self.max_stack}")

    def accepts_stack(self, stack: float) -> bool:
        return (self.min_stack is None or stack >= self.min_stack) and (
            self.max_stack is None or stack <= self.max_stack
        )

    def accepts_node(self, tree: GameTree, node: Node) -> bool:
        return (
            node.actor is not None
            and (not self.positions or node.actor in self.positions)
            and (not self.types or spot_type(tree, node) in self.types)
        )


@dataclass(frozen=True)
class Spot:
    """A question of the trainer and its answer key.

    ``history``: actions before the node, in order. ``cards``: a combo of the
    class, highest rank first (None if the solution does not use the 169 classes). ``strategy``
    and ``action_ev`` (conditional EV, bb) are those of the hand, per action.
    """

    fingerprint: str
    stack: float
    node_id: str
    hero: Position
    spot_type: SpotType
    history: tuple[tuple[Position, Action], ...]
    hand_class: int
    cards: tuple[int, int] | None
    actions: tuple[Action, ...]
    strategy: NDArray[np.float64] = field(repr=False)
    action_ev: NDArray[np.float64] = field(repr=False)

    @property
    def hand(self) -> str:
        return format_class(self.hand_class)

    @property
    def cards_text(self) -> str:
        return "" if self.cards is None else "".join(format_card(c) for c in self.cards)


def _histories(tree: GameTree) -> dict[str, tuple[tuple[Position, Action], ...]]:
    histories: dict[str, tuple[tuple[Position, Action], ...]] = {ROOT_ID: ()}
    for node in tree:  # parents come before their children
        if node.actor is None:
            continue
        for action, child in zip(node.actions, node.children, strict=True):
            histories[child] = (*histories[node.id], (node.actor, action))
    return histories


@dataclass(frozen=True)
class _Candidate:
    fingerprint: str
    solution: Solution
    stack: float
    nodes: tuple[Node, ...]
    probabilities: NDArray[np.float64]


def _candidate(fingerprint: str, solution: Solution, filters: SpotFilters) -> _Candidate | None:
    stack = min(solution.config.stacks)
    if not filters.accepts_stack(stack):
        return None
    tree = solution.tree
    nodes = tuple(node for node in tree if filters.accepts_node(tree, node))
    if not nodes:
        return None
    values = solution.values

    def weight(node: Node) -> NDArray[np.float64]:
        assert node.actor is not None  # filtered by accepts_node
        actor = int(node.actor)
        mass: NDArray[np.float64] = (
            values.reach_at(node.id)[actor] * values.opponent_mass_at(node.id)[actor]
        )
        return mass

    weights = np.stack([weight(node) for node in nodes])
    weights = np.where(np.isfinite(weights) & (weights > 0), weights, 0.0).ravel()
    total = float(weights.sum())
    if total <= 0:
        return None
    return _Candidate(fingerprint, solution, stack, nodes, weights / total)


def draw_spots(
    solutions: Mapping[str, Solution], filters: SpotFilters, count: int, seed: int
) -> list[Spot]:
    """``count`` spots passing ``filters``, reproducible with ``seed``.

    ``solutions`` maps fingerprints to solutions (the caller reads the store).
    """
    if count < 1:
        raise ValueError(f"count must be positive, got {count}")
    candidates = [
        candidate
        for fingerprint in sorted(solutions)
        if (candidate := _candidate(fingerprint, solutions[fingerprint], filters)) is not None
    ]
    if not candidates:
        raise ValueError("no spot matches the filters")

    rng = np.random.default_rng(seed)
    histories: dict[str, dict[str, tuple[tuple[Position, Action], ...]]] = {}
    spots: list[Spot] = []
    for _ in range(count):
        candidate = candidates[int(rng.integers(len(candidates)))]
        solution = candidate.solution
        n_classes = solution.hand_mass.shape[0]
        flat = int(rng.choice(len(candidate.probabilities), p=candidate.probabilities))
        node = candidate.nodes[flat // n_classes]
        hand = flat % n_classes
        cards: tuple[int, int] | None = None
        if n_classes == N_CLASSES:
            pair = sorted(
                (int(c) for c in COMBOS[int(rng.choice(combos_of_class(hand)))]), key=card_rank
            )
            cards = (pair[1], pair[0])  # highest rank first, as written (AKs, 74o)
        if candidate.fingerprint not in histories:
            histories[candidate.fingerprint] = _histories(solution.tree)
        view = solution.node(node.id)
        spots.append(
            Spot(
                fingerprint=candidate.fingerprint,
                stack=candidate.stack,
                node_id=node.id,
                hero=view.actor,
                spot_type=spot_type(solution.tree, node),
                history=histories[candidate.fingerprint][node.id],
                hand_class=hand,
                cards=cards,
                actions=node.actions,
                strategy=np.array(view.strategy[:, hand]),
                action_ev=np.array(view.action_ev[:, hand]),
            )
        )
    return spots
