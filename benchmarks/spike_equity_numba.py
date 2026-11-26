"""Spike #8 (Numba part): same measures with a Numba prototype of the fast evaluator.

Measurement only; the prototype is not part of the engine. Numba is a project
dependency since decision D-010 (it was first measured in a throw-away
environment with ``uv run --with numba``). Run:

    uv run python benchmarks/spike_equity_numba.py

The prototype reuses the 8192-entry tables of ``engine.evaluator.fast`` and is
first checked against ``evaluate_batch`` on random hands.
"""

import math
import os
import platform
import time

import numba
import numpy as np
from numba import njit, prange
from numpy.typing import NDArray

from engine.evaluator import evaluate_batch
from engine.evaluator.fast import POPCOUNT, STRAIGHT_HIGH, TOP_MASK, TOP_PACKED

SEED = 20261126
POP = np.ascontiguousarray(POPCOUNT)
SH = np.ascontiguousarray(STRAIGHT_HIGH)
TP = np.ascontiguousarray(TOP_PACKED)
TM = np.ascontiguousarray(TOP_MASK)


@njit(cache=False, inline="always")
def eval_masks(m0: int, m1: int, m2: int, m3: int) -> int:
    """Encoded rank from the four suit masks (same logic as evaluate_batch)."""
    any_ = m0 | m1 | m2 | m3
    flush = 0
    if POP[m0] >= 5:
        flush = m0
    elif POP[m1] >= 5:
        flush = m1
    elif POP[m2] >= 5:
        flush = m2
    elif POP[m3] >= 5:
        flush = m3
    if flush:
        high = SH[flush]
        if high >= 0:
            return (8 << 20) | TP[1, 1 << high]
    quads = m0 & m1 & m2 & m3
    if quads:
        return (7 << 20) | TP[1, quads] | (TP[1, any_ & ~quads] >> 4)
    ge3 = (m0 & m1 & m2) | (m0 & m1 & m3) | (m0 & m2 & m3) | (m1 & m2 & m3)
    ge2 = (m0 & m1) | (m0 & m2) | (m0 & m3) | (m1 & m2) | (m1 & m3) | (m2 & m3)
    trips = ge3 & ~quads
    pairs = ge2 & ~ge3
    if trips:
        full_pair = (trips & ~TM[1, trips]) | pairs
        if full_pair:
            return (6 << 20) | TP[1, trips] | (TP[1, full_pair] >> 4)
    if flush:
        return (5 << 20) | TP[5, flush]
    high = SH[any_]
    if high >= 0:
        return (4 << 20) | TP[1, 1 << high]
    if trips:
        return (3 << 20) | TP[1, trips] | (TP[2, any_ & ~trips] >> 4)
    if POP[pairs] >= 2:
        return (2 << 20) | TP[2, pairs] | (TP[1, any_ & ~TM[2, pairs]] >> 8)
    if pairs:
        return (1 << 20) | TP[1, pairs] | (TP[3, any_ & ~pairs] >> 4)
    return TP[5, any_]


@njit(cache=False, inline="always")
def bit_in_suit(c: int, suit: int) -> int:
    """Rank bit of card ``c`` if it has this suit, else 0."""
    return (1 << (c >> 2)) if (c & 3) == suit else 0


@njit(cache=False, inline="always")
def eval_hand(b0: int, b1: int, b2: int, b3: int, c1: int, c2: int) -> int:
    """Rank of two hole cards added to the board suit masks."""
    return eval_masks(
        b0 | bit_in_suit(c1, 0) | bit_in_suit(c2, 0),
        b1 | bit_in_suit(c1, 1) | bit_in_suit(c2, 1),
        b2 | bit_in_suit(c1, 2) | bit_in_suit(c2, 2),
        b3 | bit_in_suit(c1, 3) | bit_in_suit(c2, 3),
    )


@njit(cache=False, parallel=True)
def eval_batch(hands: NDArray[np.int64]) -> NDArray[np.int64]:
    out = np.empty(hands.shape[0], dtype=np.int64)
    for i in prange(hands.shape[0]):
        m0 = m1 = m2 = m3 = 0
        for j in range(hands.shape[1]):
            c = hands[i, j]
            m0 |= bit_in_suit(c, 0)
            m1 |= bit_in_suit(c, 1)
            m2 |= bit_in_suit(c, 2)
            m3 |= bit_in_suit(c, 3)
        out[i] = eval_masks(m0, m1, m2, m3)
    return out


@njit(cache=False, inline="always")
def accumulate(b: NDArray[np.int64], h: NDArray[np.int64], sums: NDArray[np.float64]) -> None:
    """Add the 3-way shares (sums[0:3]) and heads-up shares (sums[3:6]) of one board."""
    v0 = eval_hand(b[0], b[1], b[2], b[3], h[0], h[1])
    v1 = eval_hand(b[0], b[1], b[2], b[3], h[2], h[3])
    v2 = eval_hand(b[0], b[1], b[2], b[3], h[4], h[5])
    best = max(v0, v1, v2)
    n_win = (v0 == best) + (v1 == best) + (v2 == best)
    sums[0] += (v0 == best) / n_win
    sums[1] += (v1 == best) / n_win
    sums[2] += (v2 == best) / n_win
    sums[3] += (v0 > v1) + 0.5 * (v0 == v1)
    sums[4] += (v0 > v2) + 0.5 * (v0 == v2)
    sums[5] += (v1 > v2) + 0.5 * (v1 == v2)


@njit(cache=False)
def monte_carlo(rows: NDArray[np.int64], n: int, seed: int) -> NDArray[np.float64]:
    """``n`` draws (combo triplet then board); returns summed shares (6,)."""
    np.random.seed(seed)
    sums = np.zeros(6)
    deck = np.empty(52, dtype=np.int64)
    b = np.zeros(4, dtype=np.int64)
    for _ in range(n):
        h = rows[np.random.randint(rows.shape[0])]
        size = 0
        for c in range(52):
            if c != h[0] and c != h[1] and c != h[2] and c != h[3] and c != h[4] and c != h[5]:
                deck[size] = c
                size += 1
        b[:] = 0
        for k in range(5):  # partial Fisher-Yates
            j = k + np.random.randint(size - k)
            deck[k], deck[j] = deck[j], deck[k]
            b[deck[k] & 3] |= 1 << (deck[k] >> 2)
        accumulate(b, h, sums)
    return sums


@njit(cache=False, parallel=True)
def monte_carlo_parallel(
    rows: NDArray[np.int64], n_chunks: int, n: int, seed: int
) -> NDArray[np.float64]:
    out = np.zeros((n_chunks, 6))
    for chunk in prange(n_chunks):
        out[chunk] = monte_carlo(rows, n, seed + chunk)
    return out


@njit(cache=False)
def exhaustive_from(h: NDArray[np.int64], first: int) -> NDArray[np.float64]:
    """Summed shares over all boards whose lowest remaining-card index is ``first``."""
    deck = np.empty(46, dtype=np.int64)
    size = 0
    for c in range(52):
        if c != h[0] and c != h[1] and c != h[2] and c != h[3] and c != h[4] and c != h[5]:
            deck[size] = c
            size += 1
    sums = np.zeros(6)
    b = np.zeros(4, dtype=np.int64)
    c1 = deck[first]
    for i2 in range(first + 1, 46):
        c2 = deck[i2]
        for i3 in range(i2 + 1, 46):
            c3 = deck[i3]
            for i4 in range(i3 + 1, 46):
                c4 = deck[i4]
                for i5 in range(i4 + 1, 46):
                    c5 = deck[i5]
                    b[:] = 0
                    b[c1 & 3] |= 1 << (c1 >> 2)
                    b[c2 & 3] |= 1 << (c2 >> 2)
                    b[c3 & 3] |= 1 << (c3 >> 2)
                    b[c4 & 3] |= 1 << (c4 >> 2)
                    b[c5 & 3] |= 1 << (c5 >> 2)
                    accumulate(b, h, sums)
    return sums


@njit(cache=False)
def exhaustive(h: NDArray[np.int64]) -> NDArray[np.float64]:
    sums = np.zeros(6)
    for first in range(42):
        sums += exhaustive_from(h, first)
    return sums


@njit(cache=False, parallel=True)
def exhaustive_parallel(h: NDArray[np.int64]) -> NDArray[np.float64]:
    out = np.zeros((42, 6))
    for first in prange(42):
        out[first] = exhaustive_from(h, first)
    return out.sum(axis=0)


def timed(run: object, repeats: int = 3) -> float:
    assert callable(run)
    run()  # compilation / warm-up
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        run()
        timings.append(time.perf_counter() - start)
    return min(timings)


def main() -> None:
    import spike_equity as spike  # same folder; NumPy part of the spike

    threads = numba.get_num_threads()
    print(f"Python {platform.python_version()}, NumPy {np.__version__}, Numba {numba.__version__}")
    print(f"{platform.processor()}, {os.cpu_count()} logical CPUs, {threads} Numba threads")
    rng = np.random.default_rng(SEED)

    # Correctness of the prototype.
    hands = np.argpartition(rng.random((1_000_000, 52)), 7, axis=1)[:, :7].astype(np.int64)
    assert np.array_equal(eval_batch(hands), evaluate_batch(hands)), "prototype disagrees"
    print("\nprototype == evaluate_batch on 1,000,000 random 7-card hands: OK")

    print("\nN1 - evaluator throughput (7-card hands/s)")
    numba.set_num_threads(1)
    single = len(hands) / timed(lambda: eval_batch(hands))
    numba.set_num_threads(threads)
    parallel = len(hands) / timed(lambda: eval_batch(hands))
    print(f"  1 thread  : {single:>13,.0f}")
    print(f"  {threads} threads: {parallel:>13,.0f}")

    print("\nN2 - Monte-Carlo throughput (draws/s, 3 evaluations per draw)")
    rows = spike.compatible_triplets((0, 1, 14))
    n = 2_000_000
    mc_single = n / timed(lambda: monte_carlo(rows, n, SEED))
    n_chunks = 4 * threads
    mc_parallel = n_chunks * n / timed(lambda: monte_carlo_parallel(rows, n_chunks, n, SEED))
    print(f"  1 thread  : {mc_single:>13,.0f}")
    print(f"  {threads} threads: {mc_parallel:>13,.0f}")

    # Cross-check against the NumPy Monte-Carlo (same triplet, independent draws).
    share3, _, _ = spike.monte_carlo(rows, 400_000, rng)
    numba_sums = monte_carlo_parallel(rows, n_chunks, n, SEED + 1).sum(axis=0)
    print(
        f"  E3 NumPy {np.round(share3.mean(axis=0) * 100, 2)} vs Numba "
        f"{np.round(numba_sums[:3] / (n_chunks * n) * 100, 2)} (%)"
    )

    print("\nN3 - exhaustive enumeration of one combo triplet (1,370,754 boards)")
    h = rows[0].copy()
    numba.set_num_threads(1)
    ex_single = timed(lambda: exhaustive(h), repeats=1)
    numba.set_num_threads(threads)
    ex_parallel = timed(lambda: exhaustive_parallel(h), repeats=1)
    sums = exhaustive(h)
    assert math.isclose(sums[:3].sum(), math.comb(46, 5))
    print(f"  1 thread  : {ex_single:.3f} s")
    print(f"  {threads} threads: {ex_parallel:.3f} s")

    # Estimates, reusing the NumPy spike's measured draw counts and configuration counts.
    draws = 450_365  # M3: max error < 0.3 pt on 3000 E3 values, 95 %
    feasible = 818_532  # M4
    configs_mean = 16.5  # M4
    print("\nEstimates (Numba)")
    for label, rate in (("1 thread", mc_single), (f"{threads} threads", mc_parallel)):
        print(
            f"  full tensor, plain MC, {draws:,} draws, {label:<10}: "
            f"{feasible * draws / rate / 3600:>8,.1f} h"
        )
    for label, t in (("1 thread", ex_single), (f"{threads} threads", ex_parallel)):
        print(
            f"  exhaustive reference, 1000 triplets, {label:<10}: "
            f"{1000 * configs_mean * t / 3600:>8,.2f} h"
        )
        print(
            f"  exhaustive FULL tensor, {feasible:,} triplets, {label:<10}: "
            f"{feasible * configs_mean * t / 3600:>8,.0f} h"
        )


if __name__ == "__main__":
    main()
