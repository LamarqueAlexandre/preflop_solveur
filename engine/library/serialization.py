"""JSON form of what defines a solution: config, tree, profile, parameters (FR-012, D-016).

The data is plain JSON (dicts, lists, str, float, int, bool, None). Amounts are
always written as floats, so ``10`` and ``10.0`` give the same data, and the
profile entries are sorted: one content has a single form, which the
fingerprint hashes through ``canonical_json``.
"""

import json
from types import MappingProxyType
from typing import Any

from engine.game.config import GameConfig, SizingTable, TrancheSizings
from engine.game.tree import Action, ActionKind, GameTree, Node, Position, TerminalKind
from engine.library.solution import SolveParams
from engine.realization.profile import FORMAT_VERSION as PROFILE_FORMAT_VERSION
from engine.realization.profile import RealizationProfile, parse_profile
from engine.solver import DCFRParams, Exploitability

Data = dict[str, Any]


def canonical_json(data: object) -> str:
    """One text per content: sorted keys, no spaces, no NaN."""
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _floats(values: tuple[float, ...]) -> list[float]:
    return [float(value) for value in values]


# --- Config ------------------------------------------------------------------------------


def _sizings_to_data(sizings: TrancheSizings) -> Data:
    return {
        "open_raises": _floats(sizings.open_raises),
        "three_bet_multipliers": _floats(sizings.three_bet_multipliers),
        "isolation_base": None if sizings.isolation_base is None else float(sizings.isolation_base),
        "isolation_per_extra_limper": float(sizings.isolation_per_extra_limper),
    }


def _sizings_from_data(data: Data) -> TrancheSizings:
    base = data["isolation_base"]
    return TrancheSizings(
        open_raises=tuple(float(x) for x in data["open_raises"]),
        three_bet_multipliers=tuple(float(x) for x in data["three_bet_multipliers"]),
        isolation_base=None if base is None else float(base),
        isolation_per_extra_limper=float(data["isolation_per_extra_limper"]),
    )


def config_to_data(config: GameConfig) -> Data:
    table = config.sizing_table
    return {
        "stacks": _floats(config.stacks),
        "small_blind": float(config.small_blind),
        "big_blind": float(config.big_blind),
        "all_in_threshold": float(config.all_in_threshold),
        "realization_profile": config.realization_profile,
        "sizing_table": {
            "short": _sizings_to_data(table.short),
            "medium": _sizings_to_data(table.medium),
            "deep": _sizings_to_data(table.deep),
        },
    }


def config_from_data(data: Data) -> GameConfig:
    table = data["sizing_table"]
    stacks = [float(x) for x in data["stacks"]]
    return GameConfig(
        stacks=(stacks[0], stacks[1], stacks[2]),
        small_blind=float(data["small_blind"]),
        big_blind=float(data["big_blind"]),
        all_in_threshold=float(data["all_in_threshold"]),
        realization_profile=str(data["realization_profile"]),
        sizing_table=SizingTable(
            short=_sizings_from_data(table["short"]),
            medium=_sizings_from_data(table["medium"]),
            deep=_sizings_from_data(table["deep"]),
        ),
    )


# --- Tree --------------------------------------------------------------------------------


def _node_to_data(node: Node) -> Data:
    return {
        "id": node.id,
        "actor": None if node.actor is None else int(node.actor),
        "actions": [[action.kind.value, float(action.amount)] for action in node.actions],
        "children": list(node.children),
        "contributions": _floats(node.contributions),
        "stacks": _floats(node.stacks),
        "folded": list(node.folded),
        "raise_level": node.raise_level,
        "terminal": None if node.terminal is None else node.terminal.value,
    }


def _triple[T](values: list[T]) -> tuple[T, T, T]:
    return values[0], values[1], values[2]


def _node_from_data(data: Data) -> Node:
    actor = data["actor"]
    terminal = data["terminal"]
    return Node(
        id=str(data["id"]),
        actor=None if actor is None else Position(actor),
        actions=tuple(Action(ActionKind(kind), float(amount)) for kind, amount in data["actions"]),
        children=tuple(str(child) for child in data["children"]),
        contributions=_triple([float(x) for x in data["contributions"]]),
        stacks=_triple([float(x) for x in data["stacks"]]),
        folded=_triple([bool(x) for x in data["folded"]]),
        raise_level=int(data["raise_level"]),
        terminal=None if terminal is None else TerminalKind(terminal),
    )


def tree_to_data(tree: GameTree) -> list[Data]:
    """Nodes in the tree order (depth first); the config is serialized apart."""
    return [_node_to_data(node) for node in tree]


def tree_from_data(config: GameConfig, data: list[Data]) -> GameTree:
    nodes = [_node_from_data(entry) for entry in data]
    return GameTree(config=config, nodes=MappingProxyType({node.id: node for node in nodes}))


# --- Realization profile -----------------------------------------------------------------


def profile_to_data(profile: RealizationProfile) -> Data:
    """The profile file format (``parse_profile`` reads it back), entries sorted."""
    entries: list[Data] = []
    contexts = [(key, None, factor) for key, factor in profile.factors.items()]
    contexts += [(key, cat, factor) for (key, cat), factor in profile.category_factors.items()]
    for key, category, factor in contexts:
        entry: Data = {
            "players": key.players,
            "pot_type": key.pot_type.value,
            "tranche": key.tranche.value,
            "position": key.position.value,
            "factor": float(factor),
        }
        if category is not None:
            entry["hand_category"] = category
        entries.append(entry)
    entries.sort(
        key=lambda e: (
            e["players"],
            e["pot_type"],
            e["tranche"],
            e["position"],
            e.get("hand_category", ""),
        )
    )
    return {
        "format_version": PROFILE_FORMAT_VERSION,
        "name": profile.name,
        "version": profile.version,
        "description": profile.description,
        "entries": entries,
    }


def profile_from_data(data: Data) -> RealizationProfile:
    return parse_profile(data)


# --- Parameters and exploitability -------------------------------------------------------


def params_to_data(params: SolveParams) -> Data:
    dcfr = params.dcfr
    return {
        "max_iterations": int(params.max_iterations),
        "target_percent": float(params.target_percent),
        "check_every": int(params.check_every),
        "dcfr": {
            "alpha": float(dcfr.alpha),
            "beta": float(dcfr.beta),
            "gamma": float(dcfr.gamma),
        },
    }


def params_from_data(data: Data) -> SolveParams:
    dcfr = data["dcfr"]
    return SolveParams(
        max_iterations=int(data["max_iterations"]),
        target_percent=float(data["target_percent"]),
        check_every=int(data["check_every"]),
        dcfr=DCFRParams(
            alpha=float(dcfr["alpha"]), beta=float(dcfr["beta"]), gamma=float(dcfr["gamma"])
        ),
    )


def exploitability_to_data(result: Exploitability) -> Data:
    """Stored values plus the derived NashConv, for a readable manifest."""
    return {
        "ev": list(result.ev),
        "best_response_values": list(result.best_response_values),
        "starting_pot": float(result.starting_pot),
        "gains": list(result.gains),
        "nash_conv": result.nash_conv,
        "percent": result.percent,
    }


def exploitability_from_data(data: Data) -> Exploitability:
    ev = [float(x) for x in data["ev"]]
    best = [float(x) for x in data["best_response_values"]]
    return Exploitability(
        ev=_triple(ev), best_response_values=_triple(best), starting_pot=float(data["starting_pot"])
    )
