"""Fictitious play on the 3-max push/fold game, independent of ``engine.solver`` (SC-002.2, D-004).

Brown (1951), *Iterative solution of games by fictitious play*. At every
iteration each player plays a pure best response to the average strategies of
the others, then every average moves towards its best response:

    avg_{t+1} = avg_t + (BR_t - avg_t) / (t + 1)

Every player acts at most once per hand, so the reach of a player's own
decision nodes is 1 and averaging behaviour strategies node by node is exact.

Written from scratch to cross-check the DCFR solver: the game (6 decision
nodes, 7 terminals) and its payoffs are spelled out here; only the equity
tensors W, E3 and E2 are shared. Equal stacks only, hence no side pot. The
counterfactual value of hand h of player i at terminal z is

    v_iz(h) = sum_{x, y} W[h, x, y] r_jz(x) r_kz(y) u_iz(h, x, y)

with j < k the opponents and r their reach on the path to z. Payoffs are net
gains in bb since the start of the hand, posted blinds included (D-007).
"""

from collections.abc import Mapping
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

Vector = NDArray[np.float64]

BTN, SB, BB = 0, 1, 2
SMALL_BLIND: Final = 0.5
BIG_BLIND: Final = 1.0
N_PLAYERS: Final = 3

DECISION_NODES: Final = ("root", "F", "F-A", "A", "A-F", "A-C")
"""Decision nodes, named like the same line of the full tree."""
ACTORS: Final = {"root": BTN, "F": SB, "F-A": BB, "A": SB, "A-F": BB, "A-C": BB}

_PATHS: Final = {
    "F-F": (("root", 0), ("F", 0)),
    "F-A-F": (("root", 0), ("F", 1), ("F-A", 0)),
    "F-A-C": (("root", 0), ("F", 1), ("F-A", 1)),
    "A-F-F": (("root", 1), ("A", 0), ("A-F", 0)),
    "A-F-C": (("root", 1), ("A", 0), ("A-F", 1)),
    "A-C-F": (("root", 1), ("A", 1), ("A-C", 0)),
    "A-C-C": (("root", 1), ("A", 1), ("A-C", 1)),
}
"""Terminals: the (node, action) steps leading to them; action 1 is push or call."""
TERMINALS: Final = tuple(_PATHS)

# Payoff tensors in the frame (own hand, lower opponent, higher opponent)
_W, _WE3, _WE2_LOW, _WE2_HIGH = range(4)


def _others(player: int) -> tuple[int, int]:
    j, k = (p for p in range(N_PLAYERS) if p != player)
    return j, k


def _payoff_coefficients(stack: float) -> NDArray[np.float64]:
    """Array (players, terminals, tensors): u_iz as a sum of amount * tensor."""
    coefficients = np.zeros((N_PLAYERS, len(TERMINALS), 4))
    for z, path in enumerate(_PATHS.values()):
        contributions = [0.0, SMALL_BLIND, BIG_BLIND]
        live = [True] * N_PLAYERS
        for node, action in path:
            if action:
                contributions[ACTORS[node]] = stack
            else:
                live[ACTORS[node]] = False
        pot = sum(contributions)
        players_in = [p for p in range(N_PLAYERS) if live[p]]
        for i in range(N_PLAYERS):
            coefficients[i, z, _W] -= contributions[i]
            if not live[i]:
                continue
            if len(players_in) == 1:
                coefficients[i, z, _W] += pot
            elif len(players_in) == 3:
                coefficients[i, z, _WE3] += pot
            else:
                (opponent,) = (p for p in players_in if p != i)
                low, _ = _others(i)
                coefficients[i, z, _WE2_LOW if opponent == low else _WE2_HIGH] += pot
    return coefficients


class PushFoldFictitiousPlay:
    """Fictitious play on the 3-max push/fold game with equal stacks.

    A strategy profile maps each decision node to the probability, per hand
    class, of its aggressive action (push when unopened, call facing a push).
    """

    def __init__(self, w: ArrayLike, e3: ArrayLike, e2: ArrayLike, stack: float) -> None:
        """``w[a, b, c]``: card-disjoint combo triplets; ``e3[a, b, c]``: share of a in a
        three-way pot; ``e2[a, b, c]``: share of a against b, c being dead."""
        if stack <= BIG_BLIND:
            raise ValueError(f"push/fold needs a stack above the big blind, got {stack}")
        weights = np.asarray(w, dtype=np.float64)
        three = np.asarray(e3, dtype=np.float64)
        two = np.asarray(e2, dtype=np.float64)
        n = weights.shape[0] if weights.ndim == 3 else -1
        if n < 1 or any(t.shape != (n, n, n) for t in (weights, three, two)):
            raise ValueError(
                f"W, E3 and E2 must share a shape (n, n, n), got "
                f"{weights.shape}, {three.shape}, {two.shape}"
            )
        possible = weights > 0
        we2 = np.where(possible, weights * np.where(possible, two, 0.0), 0.0)
        tensors = (
            weights,
            np.where(possible, weights * np.where(possible, three, 0.0), 0.0),
            we2,
            we2.transpose(0, 2, 1),
        )
        self._n = n
        self._stack = stack
        self._mass = float(weights.sum())
        self._flat = [np.ascontiguousarray(t).reshape(n, n * n) for t in tensors]
        self._coefficients = _payoff_coefficients(stack)
        self._average = {node: np.full(n, 0.5) for node in DECISION_NODES}
        self._iterations = 0

    @property
    def n_classes(self) -> int:
        return self._n

    @property
    def stack(self) -> float:
        return self._stack

    @property
    def iterations(self) -> int:
        return self._iterations

    @staticmethod
    def nodes_of(player: int) -> tuple[str, ...]:
        """Decision nodes where ``player`` acts."""
        return tuple(node for node in DECISION_NODES if ACTORS[node] == player)

    def average_strategy(self) -> dict[str, Vector]:
        """Average probability of the aggressive action at each node (uniform at start)."""
        return {node: frequency.copy() for node, frequency in self._average.items()}

    def iterate(self, n: int = 1) -> None:
        """Run ``n`` iterations; every player best-responds to the current averages."""
        for _ in range(n):
            best = self.best_response(self._average)
            t = self._iterations + 1
            for node in DECISION_NODES:
                self._average[node] += (best[node] - self._average[node]) / (t + 1)
            self._iterations = t

    def expected_values(self, profile: Mapping[str, ArrayLike]) -> tuple[float, float, float]:
        """EV of BTN, SB and BB in bb under a strategy profile."""
        checked = self._check(profile)
        values = self._terminal_values(checked)
        ev = [self._ev(values[i], self._reaches(checked, i)) for i in range(N_PLAYERS)]
        return ev[0], ev[1], ev[2]

    def best_response(self, profile: Mapping[str, ArrayLike]) -> dict[str, Vector]:
        """Pure best response of each player to the others' strategies in ``profile``.

        A hand whose two actions have exactly the same value (a node the
        opponents never reach) gets 0.5.
        """
        checked = self._check(profile)
        values = self._terminal_values(checked)
        best: dict[str, Vector] = {}
        for node in DECISION_NODES:
            v = values[ACTORS[node]]
            fold, aggressive = (self._action_value(v, node, a) for a in (0, 1))
            best[node] = np.where(aggressive > fold, 1.0, np.where(aggressive < fold, 0.0, 0.5))
        return best

    def nash_conv(self, profile: Mapping[str, ArrayLike]) -> float:
        """Sum over the players of the EV gained by a best response, in bb (D-001)."""
        checked = self._check(profile)
        best = self.best_response(checked)
        values = self._terminal_values(checked)
        total = 0.0
        for i in range(N_PLAYERS):
            deviation = dict(checked)
            deviation.update({node: best[node] for node in self.nodes_of(i)})
            total += self._ev(values[i], self._reaches(deviation, i)) - self._ev(
                values[i], self._reaches(checked, i)
            )
        return total

    # --- Internals --------------------------------------------------------------------------

    def _check(self, profile: Mapping[str, ArrayLike]) -> dict[str, Vector]:
        checked: dict[str, Vector] = {}
        for node in DECISION_NODES:
            if node not in profile:
                raise ValueError(f"no strategy for decision node {node!r}")
            frequency = np.asarray(profile[node], dtype=np.float64)
            if frequency.shape != (self._n,):
                raise ValueError(
                    f"strategy of {node!r} must have shape ({self._n},), got {frequency.shape}"
                )
            if (frequency < 0).any() or (frequency > 1).any():
                raise ValueError(f"strategy of {node!r} must hold probabilities")
            checked[node] = frequency
        return checked

    def _reaches(self, profile: Mapping[str, Vector], player: int) -> NDArray[np.float64]:
        """Reach of ``player`` at each terminal through their own actions, (terminals, n)."""
        reaches = np.ones((len(TERMINALS), self._n))
        for z, path in enumerate(_PATHS.values()):
            for node, action in path:
                if ACTORS[node] == player:
                    reaches[z] *= profile[node] if action else 1.0 - profile[node]
        return reaches

    def _terminal_values(self, profile: Mapping[str, Vector]) -> list[NDArray[np.float64]]:
        """Counterfactual values v_iz(h) of every player, each of shape (terminals, n).

        Each tensor is read once for the three players and seven terminals:
        one matrix product against the stacked opponent reach products.
        """
        n, m = self._n, len(TERMINALS)
        reaches = [self._reaches(profile, p) for p in range(N_PLAYERS)]
        columns: list[Vector] = []
        for i in range(N_PLAYERS):
            j, k = _others(i)
            columns.extend(np.outer(reaches[j][z], reaches[k][z]).ravel() for z in range(m))
        weights = np.stack(columns, axis=1)  # (n * n, players * terminals)
        contracted = [flat @ weights for flat in self._flat]  # each (n, players * terminals)
        values: list[NDArray[np.float64]] = []
        for i in range(N_PLAYERS):
            block = slice(i * m, (i + 1) * m)
            v = np.zeros((m, n))
            for kind, result in enumerate(contracted):
                v += self._coefficients[i, :, kind, None] * result[:, block].T
            values.append(v)
        return values

    @staticmethod
    def _action_value(values: NDArray[np.float64], node: str, action: int) -> Vector:
        """Sum of the terminal values below ``action`` at ``node``."""
        total = np.zeros(values.shape[1])
        for z, path in enumerate(_PATHS.values()):
            if (node, action) in path:
                total += values[z]
        return total

    def _ev(self, values: NDArray[np.float64], reaches: NDArray[np.float64]) -> float:
        return float((values * reaches).sum()) / self._mass
