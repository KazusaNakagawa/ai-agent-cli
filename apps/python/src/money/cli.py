"""Command-line entry point for the household cash-flow tools."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from . import report as report_mod
from . import store
from .categorize import uncategorized
from .importer import ImportSummary, import_paths, rebuild
from .models import OUTPUT_DIR, RULES_PATH, STORE_PATH, MoneyError, Transaction
from .rules import Rules, load_rules
from .transfers import unpaired_transfer_candidates


def _print_import(summary: ImportSummary) -> None:
    for file_report in summary.files:
        print(f"{file_report.path.name}")
        print(f"  形式 {file_report.parser} / 口座 {file_report.account} / {file_report.rows} 行")
        for check in file_report.checks:
            print(f"  {check}")
        print(f"  新規 {file_report.added} 件 / 重複スキップ {file_report.duplicates} 件")
    for path, reason in summary.skipped:
        print(f"{path.name}\n  スキップ: {reason}")
    print(
        f"\n合計: 新規 {summary.added} 件 / 重複 {summary.duplicates} 件 / "
        f"ストア {summary.stored} 件"
    )
    if summary.dry_run:
        print("(--dry-run のためストアは更新していません)")


def _cmd_import(args: argparse.Namespace, rules: Rules) -> None:
    summary = import_paths(
        [Path(p) for p in args.paths],
        store_path=args.store,
        rules=rules,
        dry_run=args.dry_run,
    )
    _print_import(summary)


def _load_classified(args: argparse.Namespace, rules: Rules) -> list[Transaction]:
    """Read the store and re-derive its classifications from the current rules.

    The stored category and transfer flags are a cache of the last import. Using
    them as-is would mean editing the rules file appears to do nothing until the
    next import, which is exactly when a person is iterating on those rules.
    """
    return rebuild(store.load(args.store), rules)


def _resolve_months(transactions: list[Transaction], args: argparse.Namespace) -> list[str]:
    available = report_mod.months_covered(transactions)
    if not available:
        raise MoneyError("ストアが空です。先に `import` を実行してください")
    if args.month:
        if args.month not in available:
            raise MoneyError(
                f"{args.month} の明細がありません（取り込み済み: {available[0]}〜{available[-1]}）"
            )
        return [args.month]
    if args.range:
        try:
            start, end = args.range.split(":", 1)
        except ValueError as exc:
            raise MoneyError("--range は YYYY-MM:YYYY-MM の形式で指定してください") from exc
        months = [m for m in available if start <= m <= end]
        if not months:
            raise MoneyError(f"{args.range} に該当する月がありません")
        return months
    return [available[-1]]


def _cmd_report(args: argparse.Namespace, rules: Rules) -> None:
    transactions = _load_classified(args, rules)
    months = _resolve_months(transactions, args)

    if len(months) > 1:
        text = report_mod.render_range(transactions, months)
        out_name = f"report_{months[0]}_{months[-1]}.md"
    else:
        month = months[0]
        available = report_mod.months_covered(transactions)
        index = available.index(month)
        previous = (
            report_mod.summarize_month(transactions, available[index - 1]) if index else None
        )
        text = report_mod.render_month(
            report_mod.summarize_month(transactions, month), rules, previous=previous
        )
        out_name = f"report_{month}.md"

    if args.stdout:
        print(text, end="")
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / out_name
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")


def _cmd_review(args: argparse.Namespace, rules: Rules) -> None:
    transactions = _load_classified(args, rules)
    if not transactions:
        raise MoneyError("ストアが空です。先に `import` を実行してください")

    print("=== 口座ごとのカバー期間 ===")
    spans: dict[str, list[str]] = defaultdict(list)
    for transaction in transactions:
        spans[transaction.account].append(transaction.date)
    for account, dates in sorted(spans.items()):
        print(f"  {rules.account_label(account):16} {min(dates)} 〜 {max(dates)}  {len(dates)} 件")

    print("\n=== 未分類（金額の大きい相手から）===")
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in uncategorized(transactions):
        groups[transaction.desc_key].append(transaction)
    if not groups:
        print("  なし")
    for key in sorted(groups, key=lambda k: -sum(abs(t.amount) for t in groups[k])):
        rows = groups[key]
        total = sum(t.amount for t in rows)
        print(f"  {rows[0].desc[:34]:36} {len(rows):>3} 件  合計 {total:>12,} 円")

    print("\n=== 振替候補だがペアが見つからない ===")
    unpaired = unpaired_transfer_candidates(transactions)
    if not unpaired:
        print("  なし")
    for transaction in sorted(unpaired, key=lambda t: t.date):
        print(
            f"  {transaction.date}  {rules.account_label(transaction.account):14} "
            f"{transaction.amount:>12,}  {transaction.desc[:30]}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="money", description="Import bank statements and report monthly cash flow."
    )
    parser.add_argument(
        "--store", type=Path, default=STORE_PATH, help="path to the transaction store"
    )
    parser.add_argument("--rules", type=Path, default=RULES_PATH, help="path to the rules file")
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser("import", help="import statement CSVs (directories are expanded)")
    importer.add_argument("paths", nargs="+")
    importer.add_argument(
        "--dry-run", action="store_true", help="verify and report without writing the store"
    )
    importer.set_defaults(func=_cmd_import)

    reporter = sub.add_parser("report", help="monthly cash flow and category breakdown")
    group = reporter.add_mutually_exclusive_group()
    group.add_argument("--month", help="YYYY-MM (default: the most recent month stored)")
    group.add_argument("--range", help="YYYY-MM:YYYY-MM")
    reporter.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    reporter.set_defaults(func=_cmd_report)

    reviewer = sub.add_parser("review", help="what still needs a human: unclassified, unpaired")
    reviewer.set_defaults(func=_cmd_review)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        rules = load_rules(args.rules)
        args.func(args, rules)
    except MoneyError as exc:
        # Written for a person at a terminal; a traceback would only bury it.
        raise SystemExit(str(exc)) from exc
