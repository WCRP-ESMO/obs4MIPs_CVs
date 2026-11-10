"""Shared fixtures for the CVs repo tests."""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ValueError(f"duplicate JSON keys: {sorted(dupes)}")
    return dict(pairs)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def raw_text(repo_root) -> str:
    return (repo_root / "global_attributes.json").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def doc(raw_text) -> dict:
    """global_attributes.json, parsed; fails on duplicate keys (json would hide them)."""
    return json.loads(raw_text, object_pairs_hook=_no_duplicate_keys)


@pytest.fixture(scope="session")
def attrs(doc) -> dict:
    return doc["global_attributes"]


@pytest.fixture(scope="session")
def schema(repo_root) -> dict:
    return json.loads((repo_root / "global_attributes_schema.json").read_text())


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "esgvoc_build: full esgvoc build against the latest universe (warnings only; clones git)",
    )
