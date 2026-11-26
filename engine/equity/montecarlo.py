"""Monte-Carlo equity tensors E3 and E2 (decision D-010).

``e3[a, b, c]``: pot share of class a when a, b and c go to showdown.
``e2[a, b, c]``: share of a against b heads-up, the hand of c being dead.
Any player's value is read by reordering the indices, e.g. b in the same
three-way pot: ``e3[b, a, c]``. Impossible triplets (W = 0) hold NaN.

Only sorted triplets (a <= b <= c) are simulated; each gets its own seed,
derived from the global seed and the triplet, so the result depends neither
on the thread count nor on the subset of classes computed (principle III).
When two classes are equal, the matching players' estimates are averaged, so
the tensors are exactly symmetric.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from itertools import combinations_with_replacement, permutations
from typing import Final

import numpy as np
from numpy.typing import NDArray

from engine.cards import COMBOS, N_CLASSES, combos_of_class
from engine.equity._kernels import estimate_triplets
from engine.equity.exact import PAIRS, ThreeWayEquity
from engine.equity.weights import compute_weights

N_DRAWS: Final = 450_000
"""Draws per triplet needed for D-003 (spike #8, decision D-010)."""

_MAX_COMBOS: Final = 12


def _build_class_cards() -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    cards = np.full((N_CLASSES, _MAX_COMBOS, 2), -1, dtype=np.int64)
    sizes = np.zeros(N_CLASSES, dtype=np.int64)
    for index in range(N_CLASSES):
        combos = COMBOS[combos_of_class(index)]
        cards[index, : len(combos)] = combos
        sizes[index] = len(combos)
    return cards, sizes


_CLASS_CARDS, _CLASS_SIZES = _build_class_cards()


@dataclass(frozen=True)
class EquityTensors:
    """E3 and E2, shape (169, 169, 169), float32, with how they were computed."""

    e3: NDArray[np.float32]
    e2: NDArray[np.float32]
    n_draws: int
    seed: int


@cache
def _weights() -> NDArray[np.int32]:
    return compute_weights()


def _check_classes(classes: Sequence[int]) -> None:
    for index in classes:
        if not 0 <= index < N_CLASSES:
            raise ValueError(f"invalid class index: {index}")


def _check_draws(n_draws: int) -> None:
    if n_draws <= 0:
        raise ValueError(f"n_draws must be positive, got {n_draws}")


def triplet_seeds(triplets: NDArray[np.int64], seed: int) -> NDArray[np.int64]:
    """One 32-bit seed per sorted triplet, mixing ``seed`` and the triplet (splitmix64)."""
    code = ((triplets[:, 0] * N_CLASSES + triplets[:, 1]) * N_CLASSES + triplets[:, 2]).astype(
        np.uint64
    )
    x = np.full(len(triplets), seed % 2**64, dtype=np.uint64) * np.uint64(0x9E3779B97F4A7C15)
    x = x + code
    x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    x = x ^ (x >> np.uint64(31))
    return (x & np.uint64(0xFFFFFFFF)).astype(np.int64)


def _symmetrize(triplets: NDArray[np.int64], raw: NDArray[np.float64]) -> NDArray[np.float64]:
    """Average the estimates of players holding the same class (sorted triplets).

    Columns: 3-way shares of players 0, 1, 2, then heads-up (0,1), (0,2), (1,2).
    """
    out = raw.copy()
    eq01 = triplets[:, 0] == triplets[:, 1]
    eq12 = triplets[:, 1] == triplets[:, 2]
    both = eq01 & eq12
    only01, only12 = eq01 & ~both, eq12 & ~both

    out[only01, 0] = out[only01, 1] = (raw[only01, 0] + raw[only01, 1]) / 2
    out[only01, 3] = 0.5
    out[only01, 4] = out[only01, 5] = (raw[only01, 4] + raw[only01, 5]) / 2

    out[only12, 1] = out[only12, 2] = (raw[only12, 1] + raw[only12, 2]) / 2
    out[only12, 5] = 0.5
    out[only12, 3] = out[only12, 4] = (raw[only12, 3] + raw[only12, 4]) / 2

    out[both, :3] = 1 / 3
    out[both, 3:] = 0.5
    return out


def estimate_sorted_triplets(
    triplets: NDArray[np.int64], n_draws: int, seed: int
) -> NDArray[np.float64]:
    """Symmetrized estimates (m, 6) of feasible sorted triplets (m, 3)."""
    triplets = np.ascontiguousarray(triplets, dtype=np.int64)
    raw = estimate_triplets(
        triplets, _CLASS_CARDS, _CLASS_SIZES, n_draws, triplet_seeds(triplets, seed)
    )
    return _symmetrize(triplets, raw)


def estimate_three_way(h1: int, h2: int, h3: int, n_draws: int, seed: int) -> ThreeWayEquity:
    """Monte-Carlo E3 and E2 of one class triplet, in the given player order.

    Gives exactly the values stored in the tensors for the same seed.
    """
    classes = (h1, h2, h3)
    _check_classes(classes)
    _check_draws(n_draws)
    if _weights()[h1, h2, h3] == 0:
        raise ValueError(f"no card-disjoint combos for classes {list(classes)}")
    order = sorted(range(3), key=lambda p: classes[p])  # order[s] = player at sorted slot s
    slot = [order.index(p) for p in range(3)]
    sorted_triplet = np.array([[classes[p] for p in order]], dtype=np.int64)
    values = estimate_sorted_triplets(sorted_triplet, n_draws, seed)[0]

    three_way = (float(values[slot[0]]), float(values[slot[1]]), float(values[slot[2]]))
    heads_up = []
    for i, j in PAIRS:
        si, sj = slot[i], slot[j]
        if si < sj:
            heads_up.append(float(values[3 + PAIRS.index((si, sj))]))
        else:
            heads_up.append(1.0 - float(values[3 + PAIRS.index((sj, si))]))
    return ThreeWayEquity(three_way=three_way, heads_up=(heads_up[0], heads_up[1], heads_up[2]))


def feasible_sorted_triplets(classes: Sequence[int] | None = None) -> NDArray[np.int64]:
    """Sorted triplets (a <= b <= c) of the given classes (default: all) with W > 0."""
    pool = sorted(set(range(N_CLASSES) if classes is None else classes))
    _check_classes(pool)
    triplets = np.array(list(combinations_with_replacement(pool, 3)), dtype=np.int64)
    weights = _weights()[triplets[:, 0], triplets[:, 1], triplets[:, 2]]
    return triplets[weights > 0]


def compute_equity_tensors(
    n_draws: int = N_DRAWS,
    seed: int = 0,
    classes: Sequence[int] | None = None,
    progress: Callable[[int, int], None] | None = None,
    batch_size: int = 20_000,
) -> EquityTensors:
    """Monte-Carlo E3 and E2 for every triplet of ``classes`` (default: all 169).

    ``progress(done, total)`` is called after each batch of sorted triplets.
    Cells involving other classes, or impossible triplets, hold NaN.
    """
    _check_draws(n_draws)
    triplets = feasible_sorted_triplets(classes)
    total = len(triplets)
    estimates = np.empty((total, 6))
    for start in range(0, total, batch_size):
        stop = min(start + batch_size, total)
        estimates[start:stop] = estimate_sorted_triplets(triplets[start:stop], n_draws, seed)
        if progress is not None:
            progress(stop, total)

    e3 = np.full((N_CLASSES, N_CLASSES, N_CLASSES), np.nan, dtype=np.float32)
    e2 = np.full((N_CLASSES, N_CLASSES, N_CLASSES), np.nan, dtype=np.float32)
    x = triplets.T  # x[s] = class at sorted slot s
    for p, q, r in permutations(range(3)):
        e3[x[p], x[q], x[r]] = estimates[:, p]
    for k, (i, j) in enumerate(PAIRS):
        third = 3 - i - j
        e2[x[i], x[j], x[third]] = estimates[:, 3 + k]
        e2[x[j], x[i], x[third]] = 1.0 - estimates[:, 3 + k]
    for table in (e3, e2):
        table.flags.writeable = False
    return EquityTensors(e3=e3, e2=e2, n_draws=n_draws, seed=seed)
