"""Hand evaluators: a naive reference, a fast vectorised one and its Numba twin."""

from engine.evaluator.fast import category_of, evaluate_batch
from engine.evaluator.kernel import evaluate_batch_numba
from engine.evaluator.reference import (
    HandCategory,
    HandRank,
    compare,
    encode_rank,
    evaluate,
    evaluate_five,
)

__all__ = [
    "HandCategory",
    "HandRank",
    "category_of",
    "compare",
    "encode_rank",
    "evaluate",
    "evaluate_batch",
    "evaluate_batch_numba",
    "evaluate_five",
]
