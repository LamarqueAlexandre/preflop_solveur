"""W: number of card-disjoint combo triplets for each ordered class triplet.

``W[h1, h2, h3]`` counts the ways to deal one combo of each class with no
card in common. It carries the card removal between the three players.

Computed by inclusion-exclusion over pairs of combos. For two disjoint combos
c1 and c2, the combos of class h3 sharing no card with them number::

    size(h3) - F[c1, h3] - F[c2, h3] + B(c1, c2, h3)

where ``F[c, h]`` counts the combos of h sharing a card with c, and
``B`` the combos of h3 sharing a card with both c1 and c2 (made of one card
of c1 and one card of c2). Summing over the disjoint pairs (c1, c2) gives W.
"""

import numpy as np
from numpy.typing import NDArray

from engine.cards import (
    CLASS_OF_COMBO,
    CLASS_WEIGHTS,
    COMBOS,
    N_CARDS,
    N_CLASSES,
    N_COMBOS,
    combos_of_class,
)


def _class_of_card_pair() -> NDArray[np.int64]:
    """(52, 52) table: class of the combo made of two distinct cards (-1 on the diagonal)."""
    table = np.full((N_CARDS, N_CARDS), -1, dtype=np.int64)
    table[COMBOS[:, 0], COMBOS[:, 1]] = CLASS_OF_COMBO
    table[COMBOS[:, 1], COMBOS[:, 0]] = CLASS_OF_COMBO
    return table


def compute_weights() -> NDArray[np.int32]:
    """Return W, shape (169, 169, 169), invariant under permutation of the axes."""
    combos = COMBOS.astype(np.int64)
    classes = CLASS_OF_COMBO.astype(np.int64)
    sizes = CLASS_WEIGHTS.astype(np.int64)

    # Card incidence (1326, 52) and class indicator (1326, 169).
    incidence = np.zeros((N_COMBOS, N_CARDS), dtype=np.int64)
    incidence[np.arange(N_COMBOS)[:, None], combos] = 1
    indicator = np.zeros((N_COMBOS, N_CLASSES), dtype=np.int64)
    indicator[np.arange(N_COMBOS), classes] = 1

    conflict = (incidence @ incidence.T) > 0  # share a card (a combo conflicts with itself)
    shared = conflict.astype(np.int64) @ indicator  # F: (1326, 169)
    disjoint = sizes[None, :] - shared  # D: combos of h disjoint from c

    # N12[h1, h2] * size(h3): every disjoint pair, before removing conflicts with c3.
    n12 = indicator.T @ disjoint  # (169, 169)
    total = n12[:, :, None] * sizes[None, None, :]

    # T[h1, h2, h3] = sum over c1 in h1 of D[c1, h2] * F[c1, h3]: c3 conflicting with c1.
    t = np.empty((N_CLASSES, N_CLASSES, N_CLASSES), dtype=np.int64)
    for h in range(N_CLASSES):
        rows = combos_of_class(h)
        t[h] = disjoint[rows].T @ shared[rows]
    total -= t + t.transpose(1, 0, 2)  # c3 conflicting with c1, then with c2

    # B: add back c3 conflicting with both, i.e. one card of c1 and one card of c2.
    first, second = np.nonzero(~conflict)  # all disjoint ordered pairs
    pair_class = _class_of_card_pair()
    base = (classes[first] * N_CLASSES + classes[second]) * N_CLASSES
    both = np.zeros(N_CLASSES**3, dtype=np.int64)
    for i in range(2):
        for j in range(2):
            cross = pair_class[combos[first, i], combos[second, j]]
            both += np.bincount(base + cross, minlength=N_CLASSES**3)
    total += both.reshape(N_CLASSES, N_CLASSES, N_CLASSES)

    return total.astype(np.int32)
