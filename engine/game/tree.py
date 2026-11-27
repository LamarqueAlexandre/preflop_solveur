"""Preflop action tree (FR-004, FR-005, D-005, D-011).

Players act BTN -> SB -> BB. The action sets depend on the raise level:

- level 0, nobody in: fold, limp (call 1bb), sized opens, all-in;
- level 0, facing limps: fold, limp/complete, sized isolation raise, all-in;
  the unraised big blind checks instead of folding or calling;
- level 1 (facing a raise, isolation included): fold, call, sized 3-bets, all-in;
- level 2 (facing a 3-bet): fold, call, 4-bet all-in;
- level 3 (facing a 4-bet): fold, call.

A player facing a bet that covers their stack can only fold or call. Sized
raises go through ``GameConfig.raise_to`` (all-in conversion); one turning
into the all-in is merged with it.

Node identifiers are the action path, e.g. ``R2.0-F-C``; the root is ``root``.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Final

from engine.game.config import GameConfig

ROOT_ID: Final = "root"
N_PLAYERS: Final = 3


class Position(IntEnum):
    """Seat, also the player index in contributions and stacks."""

    BTN = 0
    SB = 1
    BB = 2


class ActionKind(Enum):
    FOLD = "F"
    CALL = "C"
    CHECK = "X"
    RAISE = "R"
    ALL_IN = "A"


@dataclass(frozen=True)
class Action:
    """An action; ``amount`` is the actor's total contribution after it (bb)."""

    kind: ActionKind
    amount: float

    @property
    def token(self) -> str:
        """Short label used in node identifiers: F, C, X, A or R<amount>."""
        if self.kind is ActionKind.RAISE:
            return f"R{self.amount}"
        letter: str = self.kind.value
        return letter


class TerminalKind(Enum):
    FOLD = "fold"  # a single player left: wins the pot
    SHOWDOWN = "showdown"  # no more betting possible: exact equity
    FLOP = "flop"  # at least two players with chips behind: equity realization


@dataclass(frozen=True)
class Node:
    """A decision point (``actor`` set) or a terminal (``terminal`` set).

    ``contributions`` and ``stacks`` (chips left) are indexed by Position.
    ``raise_level``: 0 unraised, 1 raised, 2 3-bet, 3 4-bet.
    ``children[k]`` is the identifier reached by ``actions[k]``.
    """

    id: str
    actor: Position | None
    actions: tuple[Action, ...]
    children: tuple[str, ...]
    contributions: tuple[float, float, float]
    stacks: tuple[float, float, float]
    folded: tuple[bool, bool, bool]
    raise_level: int
    terminal: TerminalKind | None

    @property
    def is_terminal(self) -> bool:
        return self.terminal is not None

    @property
    def pot(self) -> float:
        return sum(self.contributions)


@dataclass(frozen=True)
class GameTree:
    """All nodes of a configuration, by identifier, in depth-first order."""

    config: GameConfig
    nodes: Mapping[str, Node] = field(compare=False)

    @property
    def root(self) -> Node:
        return self.nodes[ROOT_ID]

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def __iter__(self) -> Iterator[Node]:
        return iter(self.nodes.values())

    def __len__(self) -> int:
        return len(self.nodes)


@dataclass
class _State:
    contributions: list[float]
    folded: list[bool]
    current_bet: float
    raise_level: int
    acted: set[int]


def _remaining(config: GameConfig, state: _State, player: int) -> float:
    return config.stacks[player] - state.contributions[player]


def _next_actor(config: GameConfig, state: _State, start: int) -> int | None:
    """First player from ``start`` (in seat order) who still has to act."""
    for offset in range(N_PLAYERS):
        player = (start + offset) % N_PLAYERS
        if state.folded[player] or _remaining(config, state, player) <= 0:
            continue
        if player not in state.acted or state.contributions[player] < state.current_bet:
            return player
    return None


def _limpers(state: _State) -> int:
    """Players besides the big blind who just called it (SB complete included)."""
    return sum(
        1
        for p in range(N_PLAYERS)
        if p != Position.BB and not state.folded[p] and state.contributions[p] >= state.current_bet
    )


def _sized_raises(config: GameConfig, state: _State, player: int) -> list[float]:
    sizings = config.sizings
    if state.raise_level == 0:
        n_limpers = _limpers(state)
        if n_limpers == 0:
            targets: tuple[float, ...] = sizings.open_raises
        else:
            isolation = sizings.isolation_size(n_limpers)
            targets = () if isolation is None else (isolation,)
    elif state.raise_level == 1:
        targets = sizings.three_bet_sizes(state.current_bet)
    else:
        return []
    stack = config.stacks[player]
    amounts: list[float] = []
    for target in targets:
        amount = config.raise_to(target, stack)
        if state.current_bet < amount < stack and amount not in amounts:
            amounts.append(amount)
    return amounts


def _actions(config: GameConfig, state: _State, player: int) -> list[Action]:
    stack = config.stacks[player]
    fold = Action(ActionKind.FOLD, state.contributions[player])
    if stack <= state.current_bet:  # facing a bet that covers the stack
        return [fold, Action(ActionKind.CALL, stack)]
    if state.contributions[player] == state.current_bet:  # unraised big blind
        actions = [Action(ActionKind.CHECK, state.current_bet)]
    else:
        actions = [fold, Action(ActionKind.CALL, state.current_bet)]
    actions += [Action(ActionKind.RAISE, a) for a in _sized_raises(config, state, player)]
    if state.raise_level < 3:
        actions.append(Action(ActionKind.ALL_IN, stack))
    return actions


def _apply(state: _State, player: int, action: Action) -> _State:
    contributions = list(state.contributions)
    folded = list(state.folded)
    current_bet, raise_level, acted = state.current_bet, state.raise_level, set(state.acted)
    if action.kind is ActionKind.FOLD:
        folded[player] = True
        acted.add(player)
    else:
        contributions[player] = action.amount
        if action.amount > current_bet:
            current_bet = action.amount
            raise_level += 1
            acted = {player}
        else:
            acted.add(player)
    return _State(contributions, folded, current_bet, raise_level, acted)


def _terminal_kind(config: GameConfig, state: _State) -> TerminalKind:
    live = [p for p in range(N_PLAYERS) if not state.folded[p]]
    if len(live) == 1:
        return TerminalKind.FOLD
    behind = [p for p in live if _remaining(config, state, p) > 0]
    return TerminalKind.SHOWDOWN if len(behind) <= 1 else TerminalKind.FLOP


def _child_id(parent: str, action: Action) -> str:
    return action.token if parent == ROOT_ID else f"{parent}-{action.token}"


def build_tree(config: GameConfig) -> GameTree:
    """Build every node of the preflop tree of ``config``."""
    nodes: dict[str, Node] = {}
    blinds = [0.0, config.small_blind, config.big_blind]
    start = _State(blinds, [False] * N_PLAYERS, config.big_blind, 0, set())

    def visit(node_id: str, state: _State, actor: int | None) -> None:
        contributions = (state.contributions[0], state.contributions[1], state.contributions[2])
        stacks = (
            config.stacks[0] - contributions[0],
            config.stacks[1] - contributions[1],
            config.stacks[2] - contributions[2],
        )
        folded = (state.folded[0], state.folded[1], state.folded[2])
        if actor is None:
            nodes[node_id] = Node(
                node_id,
                None,
                (),
                (),
                contributions,
                stacks,
                folded,
                state.raise_level,
                _terminal_kind(config, state),
            )
            return
        actions = tuple(_actions(config, state, actor))
        children = tuple(_child_id(node_id, action) for action in actions)
        nodes[node_id] = Node(
            node_id,
            Position(actor),
            actions,
            children,
            contributions,
            stacks,
            folded,
            state.raise_level,
            None,
        )
        for action, child in zip(actions, children, strict=True):
            after = _apply(state, actor, action)
            live = sum(1 for f in after.folded if not f)
            following = None if live == 1 else _next_actor(config, after, actor + 1)
            visit(child, after, following)

    visit(ROOT_ID, start, Position.BTN)
    return GameTree(config=config, nodes=MappingProxyType(nodes))
