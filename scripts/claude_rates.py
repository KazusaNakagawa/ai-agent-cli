"""Thin wrapper — the pricing table lives in apps/python/src/claude_rates.py.

Kept so standalone scripts (sdd_token_cost.py) and their tests keep
importing ``claude_rates`` from the scripts directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "python"))

from src.claude_rates import RATES, rate_for, usage_cost  # noqa: E402,F401
