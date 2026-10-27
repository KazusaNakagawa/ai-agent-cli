#!/usr/bin/env python3
"""Thin CLI wrapper — the checker lives in apps/python/src/rate_check.py.

Kept so ``python3 scripts/check_model_rates.py`` works from the repo root, as
the other scripts here do. The daily ``model-rates`` workflow imports the same
module directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "python"))

from src.rate_check import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
