"""Command-line entry point for the portfolio snapshot."""
from __future__ import annotations

import argparse
from pathlib import Path

from .models import HOLDINGS_PATH, OUTPUT_DIR, HoldingsError, load_holdings
from .render import render_snapshot
from .valuation import FX_FALLBACK, build_snapshot


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render a portfolio snapshot.")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    parser.add_argument(
        "--holdings", type=Path, default=HOLDINGS_PATH, help="path to the holdings file"
    )
    parser.add_argument(
        "--fx",
        type=float,
        default=None,
        help=f"USD/JPY to value at, instead of fetching it (fallback when the fetch fails: {FX_FALLBACK})",
    )
    args = parser.parse_args(argv)
    if args.fx is not None and args.fx <= 0:
        # Rejected here rather than rendered: every value in the snapshot is a
        # multiple of this rate, so a non-positive one has no useful output.
        parser.error(f"--fx must be a positive rate, got {args.fx}")

    try:
        holdings = load_holdings(args.holdings)
    except HoldingsError as exc:
        # The message is written for a person at a terminal; a traceback here
        # would only bury it.
        raise SystemExit(str(exc)) from exc
    text = render_snapshot(build_snapshot(holdings, fx=args.fx))

    if args.stdout:
        print(text)
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"snapshot_{holdings.as_of}.md"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
