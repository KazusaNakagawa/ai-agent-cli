"""Shared fixtures for scripts/tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import claude_rates  # noqa: E402


@pytest.fixture(autouse=True)
def reset_unpriced_warnings():
    """Clear the once-per-process unpriced-model warning cache between tests.

    The cache lives in src.claude_rates and is shared with apps/python/tests,
    so without this the first suite to aggregate an unknown model silences the
    warning for the other and the assertions become collection-order dependent.
    """
    claude_rates.reset_unpriced_warnings()
