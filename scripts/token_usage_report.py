#!/usr/bin/env python3
"""
Token usage monitoring CLI across all Claude Code projects.

Thin CLI over ``apps/python/src/usage_monitor.py`` (shared with the
``/api/usage/monitor`` endpoint): aggregates per-message ``usage`` fields
from transcript JSONL under ~/.claude/projects/ (or a given root) and
reports token counts and API-equivalent USD cost by project, date, and
model. Costs are estimates — actual usage runs on a Pro/Max subscription.

Usage:
    python3 scripts/token_usage_report.py [root] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [-v]

See https://github.com/KazusaNakagawa/ai-agent-cli/issues/362 for context.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "python"))

from src.usage_monitor import DEFAULT_ROOT, Bucket, Report, aggregate  # noqa: E402,F401

logger = logging.getLogger(__name__)


def _print_table(title: str, buckets: dict[str, Bucket]) -> None:
    print(f"## {title}")
    width = max((len(k) for k in buckets), default=4)
    for key in sorted(buckets, key=lambda k: -buckets[k].cost):
        b = buckets[key]
        print(f"  {key:<{width}}  {b.tokens:>14,} tok  ${b.cost:>10.4f}")
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Report Claude Code token usage by project/date/model."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(DEFAULT_ROOT),
        help=f"Transcript root directory (default: {DEFAULT_ROOT})",
    )
    parser.add_argument("--since", help="Start date, inclusive (YYYY-MM-DD, local time)")
    parser.add_argument("--until", help="End date, inclusive (YYYY-MM-DD, local time)")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging (per-file trace)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = Path(args.root).expanduser()
    if not root.is_dir():
        logger.error("transcript root not found: %s", root)
        sys.exit(1)

    report = aggregate(root, since=args.since, until=args.until)

    period = f" ({args.since or '...'} — {args.until or '...'})" if args.since or args.until else ""
    print(f"# Claude Code token usage report: {root}{period}\n")
    _print_table("By project", report.by_project)
    _print_table("By date", report.by_date)
    _print_table("By model", report.by_model)
    print(
        f"## Total: {report.total_tokens:,} tokens, ${report.total_cost:.4f} "
        "(API-equivalent estimate; usage is on a subscription plan)"
    )
    if report.unpriced_models:
        print(
            "  Unpriced models (excluded from cost): "
            + ", ".join(sorted(report.unpriced_models))
        )


if __name__ == "__main__":
    main()
