"""Numba kernels for equities: exhaustive enumeration and Monte-Carlo."""

import numpy as np
from numba import njit, prange

from engine.evaluator.kernel import bit_in_suit, eval_masks


@njit(cache=True, inline="always")
def hand_value(m0, m1, m2, m3, c1, c2):
    """Rank of two hole cards added to the board suit masks m0..m3."""
    return eval_masks(
        m0 | bit_in_suit(c1, 0) | bit_in_suit(c2, 0),
        m1 | bit_in_suit(c1, 1) | bit_in_suit(c2, 1),
        m2 | bit_in_suit(c1, 2) | bit_in_suit(c2, 2),
        m3 | bit_in_suit(c1, 3) | bit_in_suit(c2, 3),
    )


@njit(cache=True, inline="always")
def add_showdown(values, sums):
    """Add one board's shares: n-way in sums[:n], heads-up pairs (i < j) after."""
    n = values.shape[0]
    best = values.max()
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


@njit(cache=True)
def board_sums(hands, board):
    """Sum pot shares over every completion of ``board`` to 5 cards.

    ``hands`` holds 2 cards per player (n players), ``board`` 0 to 5 fixed
    cards. Returns ``(sums, n_boards)``: ``sums[:n]`` are the n-way shares
    (splits included), ``sums[n:]`` the heads-up shares of the first player of
    each pair (i, j), i < j, in lexicographic order, the other hands being dead.
    """
    n = hands.shape[0] // 2
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
    sums = np.zeros(n + n * (n - 1) // 2)
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
        for p in range(n):
            values[p] = hand_value(m0, m1, m2, m3, hands[2 * p], hands[2 * p + 1])
        add_showdown(values, sums)
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


@njit(cache=True)
def estimate_triplet(classes, class_cards, class_sizes, n_draws, seed):
    """Monte-Carlo mean shares (3-way, then pairs) of one class triplet.

    Each draw picks one combo per class, uniformly, rejecting shared cards (so
    every compatible combo triplet is equally likely), then a uniform board.
    The caller guarantees the triplet is feasible.
    """
    np.random.seed(seed)
    sums = np.zeros(6)
    hands = np.empty(6, dtype=np.int64)
    used = np.zeros(52, dtype=np.bool_)
    deck = np.empty(52, dtype=np.int64)
    values = np.empty(3, dtype=np.int64)
    done = 0
    while done < n_draws:
        for p in range(3):
            pick = np.random.randint(class_sizes[classes[p]])
            hands[2 * p] = class_cards[classes[p], pick, 0]
            hands[2 * p + 1] = class_cards[classes[p], pick, 1]
        clash = False
        for i in range(6):
            for j in range(i + 1, 6):
                if hands[i] == hands[j]:
                    clash = True
        if clash:
            continue

        for i in range(6):
            used[hands[i]] = True
        size = 0
        for card in range(52):
            if not used[card]:
                deck[size] = card
                size += 1
        for i in range(6):
            used[hands[i]] = False

        m0 = m1 = m2 = m3 = 0
        for k in range(5):  # partial Fisher-Yates shuffle
            j = k + np.random.randint(size - k)
            deck[k], deck[j] = deck[j], deck[k]
            card = deck[k]
            m0 |= bit_in_suit(card, 0)
            m1 |= bit_in_suit(card, 1)
            m2 |= bit_in_suit(card, 2)
            m3 |= bit_in_suit(card, 3)
        for p in range(3):
            values[p] = hand_value(m0, m1, m2, m3, hands[2 * p], hands[2 * p + 1])
        add_showdown(values, sums)
        done += 1
    return sums / n_draws


@njit(cache=True, parallel=True)
def estimate_triplets(triplets, class_cards, class_sizes, n_draws, seeds):
    """``estimate_triplet`` for each row of ``triplets``, in parallel, one seed per row."""
    out = np.zeros((triplets.shape[0], 6))
    for row in prange(triplets.shape[0]):
        out[row] = estimate_triplet(triplets[row], class_cards, class_sizes, n_draws, seeds[row])
    return out
