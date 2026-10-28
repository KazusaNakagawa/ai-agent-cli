"""Thin wrapper — the pricing table lives in apps/python/src/claude_rates.py.

Kept so standalone scripts (sdd_token_cost.py) and their tests keep
importing ``claude_rates`` from the scripts directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "python"))

from src import claude_rates as _src  # noqa: E402
from src.claude_rates import (  # noqa: E402,F401
    RATES_PATH,
    load_rates,
    rate_for,
    reset_unpriced_warnings,
    usage_cost,
)


def __getattr__(name: str):
    """Forward ``RATES`` so the re-export stays as lazy as the original.

    A plain ``from src.claude_rates import RATES`` here would resolve the table
    at import of this shim, reinstating the eager behaviour for every script
    that goes through it.
    """
    if name == "RATES":
        return _src.RATES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
