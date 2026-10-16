"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def programs_json() -> dict:
    return json.loads((FIXTURES_DIR / "programs_sample.json").read_text())


@pytest.fixture
def results_json() -> dict:
    return json.loads((FIXTURES_DIR / "results_sample.json").read_text())
