"""Portfolio snapshot — turn a holdings file into the one table every analysis needs.

Repeated position-sizing analyses stalled on the same missing input ("actual
weights and cash are unknown"), so this renders holdings + live quotes into a
single Markdown snapshot: per-position value in JPY, weight, look-through
currency exposure, bucket concentration, and pass/fail against the allocation
rules those analyses set.

Input is ``config/holdings.json`` (gitignored — see ``holdings.json.example``);
output goes to ``output/portfolio/snapshot_<date>.md``.

Layout: ``models`` (data shapes) → ``valuation`` (quotes, JPY conversion) →
``render`` (Markdown + rule verdicts), driven by ``cli``.

Usage:
    python -m src.portfolio_snapshot                 # write the snapshot file
    python -m src.portfolio_snapshot --stdout        # print instead
    python -m src.portfolio_snapshot --holdings PATH # use another holdings file
    python -m src.portfolio_snapshot --fx 150        # value at a fixed USD/JPY
"""
from .cli import main
from .models import (
    BUCKET_LABELS,
    EXAMPLE_PATH,
    HOLDINGS_PATH,
    OUTPUT_DIR,
    Holdings,
    HoldingsError,
    Position,
    Proxy,
    Snapshot,
    Valued,
    bucket_label,
    load_holdings,
)
from .render import FX_SCENARIOS, render_snapshot
from .valuation import (
    FX_FALLBACK,
    FX_SYMBOL,
    build_snapshot,
    fetch_fx,
    fetch_quotes,
    value_positions,
)

__all__ = [
    "BUCKET_LABELS",
    "EXAMPLE_PATH",
    "FX_FALLBACK",
    "FX_SCENARIOS",
    "FX_SYMBOL",
    "HOLDINGS_PATH",
    "OUTPUT_DIR",
    "Holdings",
    "HoldingsError",
    "Position",
    "Proxy",
    "Snapshot",
    "Valued",
    "bucket_label",
    "build_snapshot",
    "fetch_fx",
    "fetch_quotes",
    "load_holdings",
    "main",
    "render_snapshot",
    "value_positions",
]
