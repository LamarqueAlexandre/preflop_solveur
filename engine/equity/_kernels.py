"""Numba kernels for exact equity: enumerate every board completion."""

import numpy as np
from numba import njit, prange

from engine.evaluator.kernel import bit_in_suit, eval_masks


@njit(cache=True)
def board_sums(hands, board):
    """Sum pot shares over every completion of ``board`` to 5 cards.

    ``hands`` holds 2 cards per player (n players), ``board`` 0 to 5 fixed
    cards. Returns ``(sums, n_boards)``: ``sums[:n]`` are the n-way shares
    (splits included), ``sums[n:]`` the heads-up shares of the first player of
    each pair (i, j), i < j, in lexicographic order, the other hands being dead.
    """
    n = hands.shape[0] // 2
    n_pairs = n * (n - 1) // 2
    used = np.zeros(52, dtype=np.bool_)
    for card in hands:
        used[card] = True
    b0 = b1 = b2 = b3 = 0
    for card in board:
        used[card] = True
        b0 |= bit_in_suit(card, 0)
        b1 |= bit_in_suit(card, 1)
        b2 |= bit_in_suit(card, 2)
        b3 |= bit_in_suit(card, 3)
    deck = np.empty(52, dtype=np.int64)
    size = 0
    for card in range(52):
        if not used[card]:
            deck[size] = card
            size += 1

    r = 5 - board.shape[0]
    idx = np.arange(r)
    sums = np.zeros(n + n_pairs)
    values = np.empty(n, dtype=np.int64)
    n_boards = 0
    while True:
        m0, m1, m2, m3 = b0, b1, b2, b3
        for k in range(r):
            card = deck[idx[k]]
            m0 |= bit_in_suit(card, 0)
            m1 |= bit_in_suit(card, 1)
            m2 |= bit_in_suit(card, 2)
            m3 |= bit_in_suit(card, 3)
        best = -1
        for p in range(n):
            c1 = hands[2 * p]
            c2 = hands[2 * p + 1]
            value = eval_masks(
                m0 | bit_in_suit(c1, 0) | bit_in_suit(c2, 0),
                m1 | bit_in_suit(c1, 1) | bit_in_suit(c2, 1),
                m2 | bit_in_suit(c1, 2) | bit_in_suit(c2, 2),
                m3 | bit_in_suit(c1, 3) | bit_in_suit(c2, 3),
            )
            values[p] = value
            best = max(best, value)
        n_winners = 0
        for p in range(n):
            if values[p] == best:
                n_winners += 1
        for p in range(n):
            if values[p] == best:
                sums[p] += 1.0 / n_winners
        k = n
        for i in range(n):
            for j in range(i + 1, n):
                if values[i] > values[j]:
                    sums[k] += 1.0
                elif values[i] == values[j]:
                    sums[k] += 0.5
                k += 1
        n_boards += 1

        # Next combination of r indices among size (lexicographic order).
        i = r - 1
        while i >= 0 and idx[i] == size - r + i:
            i -= 1
        if i < 0:
            break
        idx[i] += 1
        for j in range(i + 1, r):
            idx[j] = idx[j - 1] + 1
    return sums, n_boards


@njit(cache=True, parallel=True)
def configuration_means(representatives):
    """Mean shares over all boards for each row of combos, in parallel over rows."""
    n = representatives.shape[1] // 2
    out = np.zeros((representatives.shape[0], n + n * (n - 1) // 2))
    empty_board = np.empty(0, dtype=np.int64)
    for row in prange(representatives.shape[0]):
        sums, n_boards = board_sums(representatives[row], empty_board)
        out[row] = sums / n_boards
    return out
