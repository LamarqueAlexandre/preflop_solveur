"""Restricted push/fold trees used to validate the solver (SC-002, D-004).

Heads-up sub-case: the BTN is forced to fold, the SB pushes all-in or folds
(no limp), the BB calls or folds. Node identifiers are those of the same line
in the full tree (``F``, ``F-A``, ``F-A-C``...).
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
