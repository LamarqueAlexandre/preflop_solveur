"""Restricted push/fold trees used to validate the solver (SC-002, D-004).

- 3-max game: every player pushes or folds when unopened, calls or folds
  facing a push (SC-002.2, SC-002.3).
- Heads-up sub-case: the BTN is forced to fold, the SB pushes all-in or folds
  (no limp), the BB calls or folds (SC-002.1).

Node identifiers are those of the same line in the full tree (``F``,
``F-A``, ``F-A-C``...).
"""

from types import MappingProxyType

from engine.game.config import GameConfig
from engine.game.tree import ROOT_ID, Action, ActionKind, GameTree, Node, Position, TerminalKind

_BTN_FOLDED = (True, False, False)


def build_heads_up_push_fold_tree(config: GameConfig) -> GameTree:
    """BTN folds, SB pushes or folds, BB calls or folds; unequal stacks allowed."""
    stacks = config.stacks
    if min(stacks[Position.SB], stacks[Position.BB]) <= config.big_blind:
        raise ValueError(
            f"heads-up push/fold needs SB and BB stacks above the big blind, got {stacks}"
        )
    push = stacks[Position.SB]
    call = min(push, stacks[Position.BB])
    blinds = (0.0, config.small_blind, config.big_blind)
    pushed = (0.0, push, config.big_blind)
    called = (0.0, push, call)

    def node(
        node_id: str,
        actor: Position | None,
        actions: tuple[Action, ...],
        contributions: tuple[float, float, float],
        folded: tuple[bool, bool, bool],
        raise_level: int,
        terminal: TerminalKind | None = None,
    ) -> Node:
        prefix = "" if node_id == ROOT_ID else f"{node_id}-"
        children = tuple(prefix + action.token for action in actions)
        left = (
            stacks[0] - contributions[0],
            stacks[1] - contributions[1],
            stacks[2] - contributions[2],
        )
        return Node(
            node_id, actor, actions, children, contributions, left, folded, raise_level, terminal
        )

    nodes = (
        node(
            ROOT_ID, Position.BTN, (Action(ActionKind.FOLD, 0.0),), blinds, (False, False, False), 0
        ),
        node(
            "F",
            Position.SB,
            (Action(ActionKind.FOLD, config.small_blind), Action(ActionKind.ALL_IN, push)),
            blinds,
            _BTN_FOLDED,
            0,
        ),
        node("F-F", None, (), blinds, (True, True, False), 0, TerminalKind.FOLD),
        node(
            "F-A",
            Position.BB,
            (Action(ActionKind.FOLD, config.big_blind), Action(ActionKind.CALL, call)),
            pushed,
            _BTN_FOLDED,
            1,
        ),
        node("F-A-F", None, (), pushed, (True, False, True), 1, TerminalKind.FOLD),
        node("F-A-C", None, (), called, _BTN_FOLDED, 1, TerminalKind.SHOWDOWN),
    )
    return GameTree(config=config, nodes=MappingProxyType({n.id: n for n in nodes}))


def build_push_fold_tree(config: GameConfig) -> GameTree:
    """3-max push/fold: push or fold when unopened, call or fold facing a push.

    Each player acts at most once, in the order BTN, SB, BB. A call is capped
    by the caller's stack. Callers left with chips behind check the hand down
    (no postflop betting in the push/fold game): every terminal with two or
    three live players is a showdown.
    """
    stacks = config.stacks
    if min(stacks) <= config.big_blind:
        raise ValueError(f"push/fold needs every stack above the big blind, got {stacks}")
    nodes: list[Node] = []

    def visit(
        node_id: str,
        actor: int,
        contributions: tuple[float, float, float],
        folded: tuple[bool, bool, bool],
        raise_level: int,
    ) -> None:
        left = (
            stacks[0] - contributions[0],
            stacks[1] - contributions[1],
            stacks[2] - contributions[2],
        )
        live = [p for p in range(3) if not folded[p]]
        if len(live) == 1 or actor == len(stacks):
            terminal = TerminalKind.FOLD if len(live) == 1 else TerminalKind.SHOWDOWN
            nodes.append(
                Node(node_id, None, (), (), contributions, left, folded, raise_level, terminal)
            )
            return

        fold = Action(ActionKind.FOLD, contributions[actor])
        if raise_level == 0:
            aggressive = Action(ActionKind.ALL_IN, stacks[actor])
        else:
            aggressive = Action(ActionKind.CALL, min(max(contributions), stacks[actor]))
        actions = (fold, aggressive)
        prefix = "" if node_id == ROOT_ID else f"{node_id}-"
        children = tuple(prefix + action.token for action in actions)
        nodes.append(
            Node(
                node_id,
                Position(actor),
                actions,
                children,
                contributions,
                left,
                folded,
                raise_level,
                None,
            )
        )

        folded_after = list(folded)
        folded_after[actor] = True
        visit(children[0], actor + 1, contributions, _triple(folded_after), raise_level)
        put_in = list(contributions)
        put_in[actor] = aggressive.amount
        visit(children[1], actor + 1, _triple(put_in), folded, 1)

    visit(
        ROOT_ID,
        int(Position.BTN),
        (0.0, config.small_blind, config.big_blind),
        (False, False, False),
        0,
    )
    return GameTree(config=config, nodes=MappingProxyType({n.id: n for n in nodes}))


def _triple[T](values: list[T]) -> tuple[T, T, T]:
    return values[0], values[1], values[2]
