"""Equity tensors: W (card removal), E3 and E2, and their exact reference."""

from engine.equity.exact import (
    PAIRS,
    ThreeWayEquity,
    exact_combo_equity,
    heads_up_equity,
    suit_configurations,
    three_way_equity,
)
from engine.equity.weights import compute_weights

__all__ = [
    "PAIRS",
    "ThreeWayEquity",
    "compute_weights",
    "exact_combo_equity",
    "heads_up_equity",
    "suit_configurations",
    "three_way_equity",
]
