"""Equity tensors: W (card removal), E3 and E2, and their exact reference."""

from engine.equity.exact import (
    PAIRS,
    ThreeWayEquity,
    exact_combo_equity,
    heads_up_equity,
    suit_configurations,
    three_way_equity,
)
from engine.equity.montecarlo import (
    N_DRAWS,
    EquityTensors,
    compute_equity_tensors,
    estimate_three_way,
)
from engine.equity.validation import (
    D003_MAX_POINTS,
    D003_MEAN_POINTS,
    ValidationReport,
    validate_against_exact,
)
from engine.equity.weights import compute_weights

__all__ = [
    "D003_MAX_POINTS",
    "D003_MEAN_POINTS",
    "N_DRAWS",
    "PAIRS",
    "EquityTensors",
    "ThreeWayEquity",
    "ValidationReport",
    "compute_equity_tensors",
    "compute_weights",
    "estimate_three_way",
    "exact_combo_equity",
    "heads_up_equity",
    "suit_configurations",
    "three_way_equity",
    "validate_against_exact",
]
