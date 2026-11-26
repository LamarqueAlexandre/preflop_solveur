"""Hand evaluators: a naive reference and a fast vectorised one."""

from engine.evaluator.fast import category_of, evaluate_batch
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
    "evaluate_five",
]
