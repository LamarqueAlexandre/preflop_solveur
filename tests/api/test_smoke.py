"""Smoke test: the api package is importable."""

import importlib


def test_api_is_importable() -> None:
    assert importlib.import_module("api") is not None
