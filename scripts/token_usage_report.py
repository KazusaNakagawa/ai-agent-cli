#!/usr/bin/env python3
"""
Token usage monitoring CLI across all Claude Code projects.

Aggregates per-message `usage` fields from Claude Code transcript JSONL
files under ~/.claude/projects/ (or a given root), deduped by message id,
and reports token counts and API-equivalent USD cost broken down by
project, date, and model.

Costs are estimates at published API rates — actual usage runs on a
Pro/Max subscription, not per-token billing.

Usage:
    python3 scripts/token_usage_report.py [root] [--since YYYY-MM-DD] [--until YYYY-MM-DD]

See https://github.com/KazusaNakagawa/ai-agent-cli/issues/362 for context.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from claude_rates import RATES, usage_cost

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path.home() / ".claude" / "projects"

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


@dataclass
class Bucket:
    tokens: int = 0
    cost: float = 0.0


@dataclass
class Report:
    by_project: dict[str, Bucket] = field(default_factory=dict)
    by_date: dict[str, Bucket] = field(default_factory=dict)
    by_model: dict[str, Bucket] = field(default_factory=dict)
    unpriced_models: set[str] = field(default_factory=set)

    @property
    def total_tokens(self) -> int:
        return sum(b.tokens for b in self.by_project.values())

    @property
    def total_cost(self) -> float:
        return sum(b.cost for b in self.by_project.values())


def _local_date(timestamp: str) -> str | None:
    """Convert an ISO timestamp to a local-timezone YYYY-MM-DD date."""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.astimezone().date().isoformat()


def aggregate(root: Path, since: str | None = None, until: str | None = None) -> Report:
    """Aggregate token usage from every *.jsonl transcript under root.

    Message usage entries are deduped by message id across all files, so a
    session resumed across process restarts (multiple JSONL files) is
    counted once. Entries without a message id are counted per line.
    """
    logger.info("scanning transcripts under %s (since=%s, until=%s)", root, since, until)
    report = Report()
    seen_ids: set[str] = set()
    file_count = 0
    counted = 0
    deduped = 0

    for path in sorted(root.rglob("*.jsonl")):
        project = path.relative_to(root).parts[0] if path.parent != root else path.stem
        try:
            f = open(path)
        except OSError as e:
            logger.warning("skipping unreadable file %s: %s", path, e)
            continue
        file_count += 1
        logger.debug("reading %s (project=%s)", path, project)
        with f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("skipping malformed JSON at %s:%s: %s", path, lineno, e)
                    continue

                msg = d.get("message")
                if not (isinstance(msg, dict) and isinstance(msg.get("usage"), dict)):
                    continue

                mid = msg.get("id")
                if mid:
                    if mid in seen_ids:
                        deduped += 1
                        continue
                    seen_ids.add(mid)

                date = _local_date(d.get("timestamp", ""))
                if date is None:
                    continue
                if (since and date < since) or (until and date > until):
                    continue

                counted += 1
                usage = msg["usage"]
                model = msg.get("model", "unknown")
                tokens = sum(usage.get(k, 0) for k in USAGE_KEYS)
                cost = usage_cost(usage, model)
                if model not in RATES:
                    report.unpriced_models.add(model)

                for bucket_map, key in (
                    (report.by_project, project),
                    (report.by_date, date),
                    (report.by_model, model),
                ):
                    bucket = bucket_map.setdefault(key, Bucket())
                    bucket.tokens += tokens
                    bucket.cost += cost

    logger.info(
        "aggregated %d files: %d usage entries counted, %d duplicates skipped, "
        "%d projects, total %s tokens",
        file_count,
        counted,
        deduped,
        len(report.by_project),
        f"{report.total_tokens:,}",
    )
    return report


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
