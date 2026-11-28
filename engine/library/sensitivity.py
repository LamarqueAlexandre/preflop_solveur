"""Sensitivity of the equilibrium to the realization profile (FR-008a, SC-009).

A same configuration is solved with the default profile and with variants
whose factors move by ``delta`` (SC-009: 0.1):

- ``U+`` / ``U-``: every factor + / - delta (almost neutral: only the ratios
  between factors matter, D-002);
- ``E+`` / ``E-``: the positional edge is widened / narrowed: in position and
  last to act + / - delta, out of position and first to act - / + delta,
  middle unchanged.

The strategies are compared node by node with the total variation distance
``d(h) = 1/2 sum_a |sigma_variant(a, h) - sigma_base(a, h)|``: mean weighted by
the mass of each hand at the node (actor reach x opponent hands), max and
changes of majority action over the hands reaching the node with at least
``min_reach``. See docs/notes/sensibilite-realisation.md.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

import numpy as np
from numpy.typing import NDArray

from engine.game.config import GameConfig
from engine.game.tree import GameTree, Position
from engine.library.batch import BatchEvent, run_batch
from engine.library.solution import Solution, SolveParams
from engine.library.store import SolutionStore
from engine.realization.profile import FlopPosition, RealizationKey, RealizationProfile
from engine.solver import EquityTables, NodeValues, Strategy

MODES: Final = ("U+", "U-", "E+", "E-")
"""Uniform shift (U) or positional edge (E), widened (+) or narrowed (-)."""

MIN_REACH: Final = 0.01
"""Hands reaching a node less often are ignored for the max gap and the changes."""

_EDGE: Final = {
    FlopPosition.IP: 1,
    FlopPosition.LAST: 1,
    FlopPosition.OOP: -1,
    FlopPosition.FIRST: -1,
    FlopPosition.MIDDLE: 0,
}


def perturb_profile(profile: RealizationProfile, mode: str, delta: float) -> RealizationProfile:
    """Variant of ``profile`` named ``<name>~<mode><delta>``; factors must stay positive."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}, expected one of {', '.join(MODES)}")
    if not delta > 0:
        raise ValueError(f"delta must be positive, got {delta}")
    sign = 1.0 if mode.endswith("+") else -1.0

    def shift(key: RealizationKey, factor: float) -> float:
        step = 1.0 if mode.startswith("U") else float(_EDGE[key.position])
        value = factor + sign * step * delta
        if not value > 0:
            raise ValueError(f"factor of {key} would not be positive: {factor} -> {value}")
        return value

    factors = {key: shift(key, f) for key, f in profile.factors.items()}
    categories = {(key, c): shift(key, f) for (key, c), f in profile.category_factors.items()}
    return RealizationProfile(
        name=f"{profile.name}~{mode}{delta:g}",
        version=profile.version,
        description=f"{profile.description} [sensitivity variant {mode}{delta:g}]",
        factors=MappingProxyType(factors),
        category_factors=MappingProxyType(categories),
    )


@dataclass(frozen=True)
class NodeSensitivity:
    """Gap between two strategies at one decision node.

    ``reach_probability``: probability that a hand reaches the node (base).
    ``changed``: classes whose most played action differs.
    """

    node_id: str
    actor: Position
    reach_probability: float
    mean_gap: float
    max_gap: float
    changed: tuple[int, ...]


@dataclass(frozen=True)
class StrategyComparison:
    nodes: tuple[NodeSensitivity, ...]

    @property
    def mean_gap(self) -> float:
        """Mean of the node gaps weighted by the probability of reaching each node."""
        weights = np.array([n.reach_probability for n in self.nodes])
        gaps = np.array([n.mean_gap for n in self.nodes])
        total = float(weights.sum())
        return float(weights @ gaps) / total if total > 0 else 0.0

    def most_affected(self, count: int = 5) -> tuple[NodeSensitivity, ...]:
        """Nodes with the largest gap weighted by their reach probability."""
        ranked = sorted(self.nodes, key=lambda n: n.reach_probability * n.mean_gap, reverse=True)
        return tuple(ranked[:count])


def compare_strategies(
    tree: GameTree,
    base: Mapping[str, Strategy],
    variant: Mapping[str, Strategy],
    base_values: NodeValues,
    hand_mass: NDArray[np.float64],
    min_reach: float = MIN_REACH,
) -> StrategyComparison:
    """Node-by-node gaps between ``variant`` and ``base``, weighted by the base reaches."""
    total = float(hand_mass.sum())
    nodes: list[NodeSensitivity] = []
    for node in tree:
        if node.actor is None:
            continue
        if node.id not in base or node.id not in variant:
            raise ValueError(f"node {node.id!r} is missing from one of the strategies")
        a, b = np.asarray(base[node.id]), np.asarray(variant[node.id])
        if a.shape != b.shape:
            raise ValueError(f"node {node.id!r}: strategies of different shapes")
        actor = int(node.actor)
        reach = base_values.reach_at(node.id)[actor]
        weight = reach * base_values.opponent_mass_at(node.id)[actor]
        mass = float(weight.sum())
        if mass <= 0:
            continue
        gap = 0.5 * np.abs(b - a).sum(axis=0)
        relevant = (reach >= min_reach) & (weight > 0)
        changed = relevant & (a.argmax(axis=0) != b.argmax(axis=0))
        nodes.append(
            NodeSensitivity(
                node_id=node.id,
                actor=node.actor,
                reach_probability=mass / total,
                mean_gap=float(weight @ gap) / mass,
                max_gap=float(gap[relevant].max()) if relevant.any() else 0.0,
                changed=tuple(int(c) for c in np.flatnonzero(changed)),
            )
        )
    return StrategyComparison(tuple(nodes))


def compare_solutions(
    base: Solution, variant: Solution, min_reach: float = MIN_REACH
) -> StrategyComparison:
    """``compare_strategies`` on two solutions of the same tree."""
    if list(base.tree) != list(variant.tree):
        raise ValueError("the two solutions do not share the same tree")
    return compare_strategies(
        base.tree, base.strategy, variant.strategy, base.values, base.hand_mass, min_reach
    )


@dataclass(frozen=True)
class SensitivityResult:
    stack: float
    mode: str
    delta: float
    profile_name: str
    base_nash_conv: float
    variant_nash_conv: float
    base_root_ev: tuple[float, float, float]
    variant_root_ev: tuple[float, float, float]
    comparison: StrategyComparison = field(repr=False)


def run_sensitivity(
    stacks: Sequence[float],
    modes: Sequence[str],
    delta: float,
    tables: EquityTables,
    profile: RealizationProfile,
    params: SolveParams,
    base_store: SolutionStore,
    variant_store: SolutionStore,
    on_event: Callable[[BatchEvent], None] | None = None,
) -> list[SensitivityResult]:
    """Solve (or reuse) the base and every variant at every depth, then compare them.

    Base solutions go to ``base_store`` (normally the library), variants to
    ``variant_store``; both through the idempotent batch, so a rerun solves nothing.
    """
    variants = [perturb_profile(profile, mode, delta) for mode in modes]

    def solved(store: SolutionStore, prof: RealizationProfile) -> list[Solution]:
        configs = [GameConfig.equal_stacks(s, realization_profile=prof.name) for s in stacks]
        report = run_batch(configs, tables, prof, store, params, on_event)
        return [store.load(entry.summary.fingerprint) for entry in report.entries]

    bases = solved(base_store, profile)
    by_mode = {mode: solved(variant_store, v) for mode, v in zip(modes, variants, strict=True)}
    results: list[SensitivityResult] = []
    for i, stack in enumerate(stacks):
        base = bases[i]
        for mode, variant_profile in zip(modes, variants, strict=True):
            variant = by_mode[mode][i]
            results.append(
                SensitivityResult(
                    stack=float(stack),
                    mode=mode,
                    delta=delta,
                    profile_name=variant_profile.name,
                    base_nash_conv=base.exploitability.percent,
                    variant_nash_conv=variant.exploitability.percent,
                    base_root_ev=base.root_ev(),
                    variant_root_ev=variant.root_ev(),
                    comparison=compare_solutions(base, variant),
                )
            )
    return results


def render_report(results: Sequence[SensitivityResult], hand_name: Callable[[int], str]) -> str:
    """Markdown report: one section per depth, a summary table and the most affected nodes."""
    lines = [
        "# Sensibilité au profil de réalisation (FR-008a, SC-009)",
        "",
        "Écart d(h) = ½ Σ |stratégie_variante - stratégie_défaut| : part de la stratégie",
        "qui change d'action. Moyenne pondérée par la masse de chaque main au nœud ; maximum",
        "et changements d'action majoritaire sur les mains qui atteignent le nœud à au moins",
        f"{MIN_REACH:.0%}. Tout écart est relatif au modèle (préflop avec réalisation d'équité).",
    ]
    for stack in dict.fromkeys(r.stack for r in results):
        rows = [r for r in results if r.stack == stack]
        lines += [
            "",
            f"## {stack:g}bb",
            "",
            "| Variante | Écart moyen | Nœud le plus touché (écart max) | Mains qui changent "
            "d'action majoritaire | EV racine BTN / SB / BB (défaut → variante) | NashConv |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            comparison = r.comparison
            worst = max(comparison.nodes, key=lambda n: n.max_gap)
            changes = sum(len(n.changed) for n in comparison.nodes)
            ev = " / ".join(
                f"{a:+.3f} → {b:+.3f}"
                for a, b in zip(r.base_root_ev, r.variant_root_ev, strict=True)
            )
            lines.append(
                f"| {r.mode} | {comparison.mean_gap:.2%} | {worst.node_id} ({worst.max_gap:.0%}) "
                f"| {changes} | {ev} | {r.variant_nash_conv:.3f} % |"
            )
        for r in rows:
            lines += [
                "",
                f"### {stack:g}bb, {r.mode} : nœuds les plus touchés",
                "",
                "| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |",
                "|---|---|---|---|---|---|",
            ]
            for n in r.comparison.most_affected():
                names = " ".join(hand_name(c) for c in n.changed[:15])
                more = f" (+{len(n.changed) - 15})" if len(n.changed) > 15 else ""
                lines.append(
                    f"| {n.node_id} | {n.actor.name} | {n.reach_probability:.1%} "
                    f"| {n.mean_gap:.2%} | {n.max_gap:.0%} | {names}{more} |"
                )
    return "\n".join(lines) + "\n"
