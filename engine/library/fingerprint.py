"""Fingerprint of a solution: SHA-256 of what defines it (FR-012, principle III, D-016).

The fingerprint covers the config, the tree, the realization profile (its
content, not only its name), the convergence parameters, the engine version
and the equity tensors. It can be computed before solving, so that a batch
skips the configurations already in the store.
"""

import hashlib
from typing import Any, Final

from engine.game.tree import GameTree
from engine.library.serialization import (
    canonical_json,
    config_to_data,
    params_to_data,
    profile_to_data,
    tree_to_data,
)
from engine.library.solution import Solution, SolveParams
from engine.realization.profile import RealizationProfile

FINGERPRINT_SCHEMA: Final = 1
"""Version of the fingerprint content; bumped if what is hashed changes."""


def fingerprint_data(
    tree: GameTree,
    profile: RealizationProfile,
    params: SolveParams,
    equity_digest: str,
    engine_version: str,
) -> dict[str, Any]:
    """Everything the fingerprint hashes, as JSON data."""
    return {
        "schema": FINGERPRINT_SCHEMA,
        "config": config_to_data(tree.config),
        "tree": tree_to_data(tree),
        "profile": profile_to_data(profile),
        "params": params_to_data(params),
        "engine_version": engine_version,
        "equity_digest": equity_digest,
    }


def fingerprint(
    tree: GameTree,
    profile: RealizationProfile,
    params: SolveParams,
    equity_digest: str,
    engine_version: str,
) -> str:
    """SHA-256 (64 hex characters) of the canonical JSON of ``fingerprint_data``."""
    data = fingerprint_data(tree, profile, params, equity_digest, engine_version)
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def solution_fingerprint(solution: Solution) -> str:
    """Fingerprint of a solution, from the inputs it records."""
    return fingerprint(
        solution.tree,
        solution.profile,
        solution.params,
        solution.equity_digest,
        solution.engine_version,
    )
