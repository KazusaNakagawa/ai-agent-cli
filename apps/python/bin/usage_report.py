"""log/usage/*.jsonl を集計し、label 別・日別のトークン/コスト合計を出力する。"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

USAGE_DIR = Path(__file__).parents[1] / "log" / "usage"


def _iter_records(usage_dir: Path, days: int | None):
    cutoff = None
    if days is not None:
        cutoff = (datetime.now() - timedelta(days=days)).date()
    for path in sorted(usage_dir.glob("*-usage.jsonl")):
        try:
            file_date = datetime.strptime(path.stem.replace("-usage", ""), "%Y%m%d").date()
        except ValueError:
            continue
        if cutoff is not None and file_date < cutoff:
            continue
        day = file_date.isoformat()
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield day, json.loads(line)
                except json.JSONDecodeError:
                    continue


def build_summary(usage_dir: Path, days: int | None) -> dict:
    """(day, label) ごとにトークン/コスト/呼び出し回数を集計する。"""
    summary: dict = defaultdict(lambda: {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "cost_usd": 0.0,
    })
    for day, rec in _iter_records(usage_dir, days):
        key = (day, rec.get("label", "(unknown)"))
        agg = summary[key]
        agg["calls"] += 1
        agg["input_tokens"] += rec.get("input_tokens", 0) or 0
        agg["output_tokens"] += rec.get("output_tokens", 0) or 0
        agg["cache_read_tokens"] += rec.get("cache_read_tokens", 0) or 0
        agg["cache_creation_tokens"] += rec.get("cache_creation_tokens", 0) or 0
        agg["cost_usd"] += rec.get("cost_usd", 0.0) or 0.0
    return summary


def format_summary(summary: dict) -> str:
    if not summary:
        return "No usage records found."
    header = f"{'DATE':<10}  {'LABEL':<24}  {'CALLS':>5}  {'IN':>8}  {'OUT':>8}  {'CACHE_R':>8}  {'COST_USD':>9}"
    lines = [header, "-" * len(header)]
    for (day, label), agg in sorted(summary.items()):
        lines.append(
            f"{day:<10}  {label[:24]:<24}  {agg['calls']:>5}  "
            f"{agg['input_tokens']:>8}  {agg['output_tokens']:>8}  "
            f"{agg['cache_read_tokens']:>8}  {agg['cost_usd']:>9.4f}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude token usage report")
    parser.add_argument(
        "--days", type=int, default=None,
        help="Limit lookback window to the last N days",
    )
    args = parser.parse_args()
    summary = build_summary(USAGE_DIR, args.days)
    print(format_summary(summary))


if __name__ == "__main__":
    main()
