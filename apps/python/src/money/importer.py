"""Import pipeline: decode, verify, deduplicate, classify, pair, store.

Order matters in two places. Verification runs before anything is stored, so a
file that fails its own arithmetic never enters the ledger. Transfer pairing
runs last and over the whole store rather than only the new rows, because the
matching half of a transfer is regularly imported later than the first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import store
from .categorize import categorize
from .models import MoneyError, Transaction, UnknownFormatError
from .parsers import parse_file
from .rules import Rules
from .transfers import apply_transfer_rules, pair_cross_account


@dataclass
class FileReport:
    path: Path
    parser: str
    account: str
    rows: int
    checks: list[str] = field(default_factory=list)
    added: int = 0
    duplicates: int = 0


@dataclass
class ImportSummary:
    files: list[FileReport] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    stored: int = 0
    dry_run: bool = False

    @property
    def added(self) -> int:
        return sum(f.added for f in self.files)

    @property
    def duplicates(self) -> int:
        return sum(f.duplicates for f in self.files)


def collect_files(paths: list[Path]) -> list[tuple[Path, bool]]:
    """Expand directories to the CSVs inside them, noting how each was reached.

    The flag is True when a file was named on the command line. That is the
    difference between "read this file" — where an unreadable format is an
    error — and "read this folder", where formats belonging to a later phase
    live alongside the ones this phase understands.
    """
    files: list[tuple[Path, bool]] = []
    for path in paths:
        if path.is_dir():
            files.extend((p, False) for p in sorted(path.glob("*.csv")) if p.is_file())
        elif path.is_file():
            files.append((path, True))
        else:
            raise MoneyError(f"{path}: no such file or directory")
    if not files:
        raise MoneyError("no CSV files found to import")
    return files


def rebuild(transactions: list[Transaction], rules: Rules) -> list[Transaction]:
    """Re-derive every classification from the raw rows and the current rules.

    Cheap enough to run over the whole store each time, which keeps the stored
    flags consistent with the rules file instead of frozen at import time.
    """
    transactions = categorize(transactions, rules)
    transactions = apply_transfer_rules(transactions, rules)
    return pair_cross_account(transactions)


def import_paths(
    paths: list[Path],
    *,
    store_path: Path,
    rules: Rules,
    dry_run: bool = False,
) -> ImportSummary:
    summary = ImportSummary(dry_run=dry_run)
    existing = store.load(store_path)
    merged = existing

    for path, explicit in collect_files(paths):
        # Any failure here — bad encoding, broken balance chain — raises before
        # the store is touched, so a damaged file cannot half-import.
        try:
            result = parse_file(path)
        except UnknownFormatError:
            if explicit:
                raise
            summary.skipped.append((path, "対応する形式ではありません"))
            continue
        merged, added, duplicates = store.merge(merged, result.transactions)
        summary.files.append(
            FileReport(
                path=path,
                parser=result.parser,
                account=result.account,
                rows=len(result.transactions),
                checks=result.checks,
                added=added,
                duplicates=duplicates,
            )
        )

    merged = rebuild(merged, rules)
    summary.stored = len(merged)
    if not dry_run:
        store.save(store_path, merged)
    return summary
