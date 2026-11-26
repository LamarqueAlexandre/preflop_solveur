"""Smoke test: the engine package is importable."""

import importlib


def test_engine_is_importable() -> None:
    assert importlib.import_module("engine") is not None
