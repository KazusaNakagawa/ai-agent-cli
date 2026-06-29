"""CLI entrypoint for chart generation (#14).

Usage:
    python -m src.charts price [--tickers PLTR NVDA] [--output-dir DIR] [--period 3mo]

When ``--tickers`` is omitted, the portfolio tickers from the briefing config
are used.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.charts.price_comparison import generate_price_comparison

# Default output directory: apps/python/output/charts (output/ is git-ignored).
_DEFAULT_OUTPUT_DIR = Path(__file__).parents[2] / "output" / "charts"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.charts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    price = sub.add_parser("price", help="multi-ticker price comparison chart")
    price.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="ticker symbols (default: portfolio tickers from config)",
    )
    price.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    price.add_argument(
        "--period",
        default="3mo",
        help="lookback window passed to yfinance (default: 3mo)",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    if args.cmd == "price":
        tickers = args.tickers
        if not tickers:
            # Lazy import so the config file is only read when actually needed.
            from src.config import CONFIG

            tickers = list(CONFIG.portfolio.tickers)
        out_path = generate_price_comparison(tickers, args.output_dir, args.period)
        print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
