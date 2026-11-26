"""Spike #8 (NumPy part): cost of the equity tensors W, E3, E2.

Run: ``uv run python benchmarks/spike_equity.py``
The Numba measurements live in ``spike_equity_numba.py``.
Findings are written up in ``docs/notes/spike-equites.md``.

Measures, with a fixed seed:
  M1  fast evaluator throughput by batch size;
  M2  end-to-end Monte-Carlo throughput (draw combos + board, 3 evaluations);
  M3  per-sample spread of the equity outcomes -> number of draws needed for D-003,
      and gain of stratifying by suit configuration;
  M4  number of suit-isomorphic configurations per class triplet
      -> cost of the exhaustive reference;
  M5  exhaustive enumeration cost of one combo triplet (all 1 370 754 boards).
"""

import math
import platform
import time
from itertools import combinations, combinations_with_replacement, permutations

import numpy as np
from numpy.typing import NDArray

from engine.cards import COMBOS, N_CLASSES, combos_of_class, format_class
from engine.evaluator import evaluate_batch

SEED = 20261126
N_BOARDS_PER_COMBO_TRIPLET = math.comb(46, 5)  # 1 370 754
PAIRS = ((0, 1), (0, 2), (1, 2))
SUIT_PERMUTATIONS = np.array(list(permutations(range(4))), dtype=np.int64)

ALL_CLASS_TRIPLETS = np.array(
    list(combinations_with_replacement(range(N_CLASSES), 3)), dtype=np.int64
)  # 818 805 unordered triplets


# --- Combo triplets and suit isomorphism ----------------------------------------


def compatible_triplets(classes: tuple[int, int, int]) -> NDArray[np.int64]:
    """All combo triplets of these classes without a shared card, as cards (m, 6)."""
    hands = [COMBOS[combos_of_class(c)].astype(np.int64) for c in classes]
    grid = np.meshgrid(*(np.arange(len(h)) for h in hands), indexing="ij")
    rows = np.concatenate(
        [h[g.ravel()] for h, g in zip(hands, grid, strict=True)], axis=1
    )  # (n1*n2*n3, 6)
    ordered = np.sort(rows, axis=1)
    return rows[np.all(np.diff(ordered, axis=1) > 0, axis=1)]


def suit_configurations(rows: NDArray[np.int64]) -> NDArray[np.int64]:
    """Configuration id of each combo triplet: equal ids <=> same up to a suit permutation."""
    ranks, suits = rows // 4, rows % 4
    best = np.full(len(rows), np.iinfo(np.int64).max)
    for perm in SUIT_PERMUTATIONS:
        cards = ranks * 4 + perm[suits]
        key = np.zeros(len(rows), dtype=np.int64)
        for player in range(3):
            a, b = cards[:, 2 * player], cards[:, 2 * player + 1]
            key = key * 2704 + np.minimum(a, b) * 52 + np.maximum(a, b)
        best = np.minimum(best, key)
    return np.unique(best, return_inverse=True)[1]


# --- Monte-Carlo ------------------------------------------------------------------


def draw_boards(hands: NDArray[np.int64], rng: np.random.Generator) -> NDArray[np.int64]:
    """One random 5-card board per row, avoiding the 6 hole cards of that row."""
    keys = rng.random((len(hands), 52))
    np.put_along_axis(keys, hands, 2.0, axis=1)
    return np.argpartition(keys, 5, axis=1)[:, :5]


def showdown(
    hands: NDArray[np.int64], boards: NDArray[np.int64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Pot shares: 3-way (n, 3) and heads-up for each pair (n, 3), splits included."""
    values = np.stack(
        [
            evaluate_batch(np.concatenate([hands[:, 2 * p : 2 * p + 2], boards], axis=1))
            for p in range(3)
        ],
        axis=1,
    )
    winners = values == values.max(axis=1, keepdims=True)
    share3 = winners / winners.sum(axis=1, keepdims=True)
    share2 = np.stack(
        [(values[:, i] > values[:, j]) + 0.5 * (values[:, i] == values[:, j]) for i, j in PAIRS],
        axis=1,
    )
    return share3, share2


def monte_carlo(
    rows: NDArray[np.int64], n: int, rng: np.random.Generator
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]]:
    """``n`` draws: uniform compatible combo triplet, then uniform board."""
    picked = rng.integers(len(rows), size=n)
    hands = rows[picked]
    share3, share2 = showdown(hands, draw_boards(hands, rng))
    return share3, share2, picked


# --- Measures ---------------------------------------------------------------------


def best_time(run: object, repeats: int = 3) -> float:
    assert callable(run)
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        run()
        timings.append(time.perf_counter() - start)
    return min(timings)


def random_class_triplets(n: int, rng: np.random.Generator) -> list[tuple[int, int, int]]:
    """``n`` distinct unordered class triplets drawn uniformly, keeping feasible ones."""
    chosen: list[tuple[int, int, int]] = []
    for row in rng.permutation(len(ALL_CLASS_TRIPLETS)):
        triplet = (
            int(ALL_CLASS_TRIPLETS[row, 0]),
            int(ALL_CLASS_TRIPLETS[row, 1]),
            int(ALL_CLASS_TRIPLETS[row, 2]),
        )
        if len(compatible_triplets(triplet)):
            chosen.append(triplet)
        if len(chosen) == n:
            break
    return chosen


def m1_evaluator(rng: np.random.Generator) -> None:
    print("\nM1 - fast evaluator throughput (7-card hands/s)")
    for size in (1_000, 10_000, 100_000, 1_000_000):
        hands = np.argpartition(rng.random((size, 52)), 7, axis=1)[:, :7]
        elapsed = best_time(lambda hands=hands: evaluate_batch(hands))
        print(f"  batch {size:>9,}: {size / elapsed:>12,.0f}")


def m2_monte_carlo(rng: np.random.Generator) -> float:
    print("\nM2 - Monte-Carlo throughput, NumPy (draws/s, 3 evaluations per draw)")
    rows = compatible_triplets((0, 1, 14))  # AA, AKs, KK
    n = 200_000
    elapsed = best_time(lambda: monte_carlo(rows, n, rng))
    hands = rows[rng.integers(len(rows), size=n)]
    t_boards = best_time(lambda: draw_boards(hands, rng))
    boards = draw_boards(hands, rng)
    t_eval = best_time(lambda: showdown(hands, boards))
    rate = n / elapsed
    print(f"  end to end      : {rate:>10,.0f} draws/s")
    print(f"  of which boards : {t_boards / elapsed:>10.0%} of the time")
    print(f"  of which eval   : {t_eval / elapsed:>10.0%} of the time")
    return rate


def draws_for_mean(sigmas: NDArray[np.float64], target: float) -> float:
    """Draws so that the expected mean |error| is below ``target`` (fraction)."""
    return float((math.sqrt(2 / math.pi) * sigmas.mean() / target) ** 2)


def draws_for_max(sigmas: NDArray[np.float64], target: float, confidence: float = 0.95) -> float:
    """Draws so that all errors are below ``target`` with probability ``confidence``."""

    def p_all(n: float) -> float:
        z = target * math.sqrt(n) / sigmas
        return float(np.prod(1 - np.array([math.erfc(x / math.sqrt(2)) for x in z])))

    low, high = 1.0, 1e9
    while high / low > 1.01:
        mid = math.sqrt(low * high)
        low, high = (mid, high) if p_all(mid) < confidence else (low, mid)
    return high


def m3_variance(rng: np.random.Generator) -> dict[str, float]:
    print("\nM3 - spread of outcomes and draws needed for D-003")
    triplets = random_class_triplets(300, rng)
    n = 20_000
    sig3, sig2, total_var, within_var = [], [], [], []
    for k, triplet in enumerate(triplets):
        rows = compatible_triplets(triplet)
        share3, share2, picked = monte_carlo(rows, n, rng)
        sig3.extend(share3.std(axis=0))
        sig2.extend(share2.std(axis=0))
        if k < 60:  # stratification gain on a subset
            config = suit_configurations(rows)[picked]
            counts = np.bincount(config)
            for column in share3.T:
                means = np.bincount(config, column) / np.maximum(counts, 1)
                within = column - means[config]
                total_var.append(column.var())
                within_var.append(within.var())
    s3, s2 = np.array(sig3), np.array(sig2)
    # D-003 is judged on >= 1000 class triplets, 3 three-way equities each.
    s3_sample = rng.choice(s3, size=3000)
    s2_sample = rng.choice(s2, size=3000)
    result = {
        "sigma3_mean": float(s3.mean()),
        "sigma3_max": float(s3.max()),
        "sigma2_mean": float(s2.mean()),
        "n_mean_e3": draws_for_mean(s3, 0.001),
        "n_max_e3": draws_for_max(s3_sample, 0.003),
        "n_mean_e2": draws_for_mean(s2, 0.001),
        "n_max_e2": draws_for_max(s2_sample, 0.003),
        "stratification_gain": float(np.sum(total_var) / np.sum(within_var)),
    }
    print(f"  triplets sampled: {len(triplets)}, {n:,} draws each")
    print(f"  sigma E3 per draw: mean {s3.mean():.3f}, max {s3.max():.3f}")
    print(f"  sigma E2 per draw: mean {s2.mean():.3f}, max {s2.max():.3f}")
    print(f"  draws for mean error < 0.1 pt : E3 {result['n_mean_e3']:>9,.0f}", end="")
    print(f" | E2 {result['n_mean_e2']:>9,.0f}")
    print(f"  draws for max error  < 0.3 pt : E3 {result['n_max_e3']:>9,.0f}", end="")
    print(f" | E2 {result['n_max_e2']:>9,.0f}  (3000 values, 95 %)")
    print(
        f"  variance ratio total / within suit configurations: {result['stratification_gain']:.3f}"
    )
    return result


def m4_configurations(rng: np.random.Generator) -> dict[str, float]:
    print("\nM4 - suit-isomorphic configurations per class triplet")
    picks = rng.choice(len(ALL_CLASS_TRIPLETS), size=3000, replace=False)
    n_triplets, n_configs, feasible = [], [], 0
    for row in picks:
        triplet = (
            int(ALL_CLASS_TRIPLETS[row, 0]),
            int(ALL_CLASS_TRIPLETS[row, 1]),
            int(ALL_CLASS_TRIPLETS[row, 2]),
        )
        rows = compatible_triplets(triplet)
        if not len(rows):
            continue
        feasible += 1
        n_triplets.append(len(rows))
        n_configs.append(int(suit_configurations(rows).max()) + 1)
    combo_t, configs = np.array(n_triplets), np.array(n_configs)
    result = {
        "feasible_share": feasible / len(picks),
        "combo_triplets_mean": float(combo_t.mean()),
        "configs_mean": float(configs.mean()),
        "configs_max": float(configs.max()),
    }
    print(f"  feasible class triplets: {result['feasible_share']:.2%} (of 3000 drawn)")
    print(f"  combo triplets per class triplet: mean {combo_t.mean():.0f}, max {combo_t.max()}")
    print(
        f"  suit configurations per class triplet: mean {configs.mean():.1f}, max {configs.max()}"
    )
    examples = [(0, 1, 14), (0, 14, 28), (1, 13, 28)]
    for triplet in examples:
        rows = compatible_triplets(triplet)
        label = " / ".join(format_class(c) for c in triplet)
        print(
            f"    {label:<16} {len(rows):>5} combo triplets, "
            f"{int(suit_configurations(rows).max()) + 1:>4} configurations"
        )
    return result


def m5_exhaustive(rng: np.random.Generator) -> float:
    print("\nM5 - exhaustive enumeration of one combo triplet, NumPy")
    hands = compatible_triplets((0, 1, 14))[:1]  # one AA / AKs / KK triplet
    remaining = np.setdiff1d(np.arange(52), hands[0])
    boards = remaining[np.array(list(combinations(range(46), 5)))]
    tiled = np.repeat(hands, len(boards), axis=0)
    elapsed = best_time(lambda: showdown(tiled, boards), repeats=1)
    print(f"  {len(boards):,} boards x 3 evaluations: {elapsed:.2f} s")
    return elapsed


def main() -> None:
    rng = np.random.default_rng(SEED)
    print(f"Python {platform.python_version()}, NumPy {np.__version__}, {platform.processor()}")
    m1_evaluator(rng)
    rate = m2_monte_carlo(rng)
    variance = m3_variance(rng)
    configs = m4_configurations(rng)
    exhaustive = m5_exhaustive(rng)

    print("\nEstimates (NumPy, single process)")
    n_feasible = len(ALL_CLASS_TRIPLETS) * configs["feasible_share"]
    draws = max(variance["n_max_e3"], variance["n_mean_e3"])
    hours = n_feasible * draws / rate / 3600
    print(f"  feasible unordered class triplets: {n_feasible:,.0f}")
    print(f"  full tensor, plain Monte-Carlo, {draws:,.0f} draws/triplet: {hours:,.0f} h")
    ref_hours = 1000 * configs["configs_mean"] * exhaustive / 3600
    print(f"  exhaustive reference, 1000 triplets, with suit isomorphism: {ref_hours:,.0f} h")
    no_iso = 1000 * configs["combo_triplets_mean"] * exhaustive / 3600
    print(f"  exhaustive reference, 1000 triplets, without isomorphism  : {no_iso:,.0f} h")


if __name__ == "__main__":
    main()
