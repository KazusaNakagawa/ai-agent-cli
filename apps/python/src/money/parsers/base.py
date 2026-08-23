"""Shared pieces every parser needs, kept out of the package __init__.

Parsers import from here and the registry imports the parsers, so putting these
in ``__init__`` would make the import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..models import MoneyError, Transaction
from ..normalize import match_key, normalize_description, transaction_id


@dataclass
class ParseResult:
    """One imported file: its rows plus what could be verified about them."""

    path: Path
    parser: str
    account: str
    transactions: list[Transaction]
    checks: list[str] = field(default_factory=list)


def build_transaction(
    *,
    account: str,
    date: str,
    amount: int,
    desc_raw: str,
    balance: int | None,
    source_file: str,
) -> Transaction:
    desc = normalize_description(desc_raw)
    key = match_key(desc_raw)
    return Transaction(
        id=transaction_id(account, date, amount, key, balance),
        date=date,
        account=account,
        amount=amount,
        desc_raw=desc_raw,
        desc=desc,
        desc_key=key,
        balance=balance,
        source_file=source_file,
    )


def verify_calendar_date(value: str, *, path: Path, line: int) -> str:
    """Reject a date that has the right shape but is not a day that exists.

    The shape check each parser runs cannot tell ``2026-02-30`` from a real
    date. Letting one through would file the row under a month that never
    happened and blow up later, deep in transfer pairing, with a bare
    ``ValueError`` instead of a message naming the file and line.
    """
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise MoneyError(f"{path.name} line {line}: {value} is not a real date") from exc
    return value


def verify_balance_chain(rows: list[tuple[int, int | None]], *, path: Path) -> str:
    """Check that each running balance follows from the previous one.

    ``rows`` is ``(amount, balance)`` in the order the file lists them. This is
    the only check that proves nothing was dropped, duplicated, or mistyped —
    it is what makes transcribing a statement from screenshots trustworthy.
    """
    if not rows:
        return "balance chain: skipped (no rows)"
    previous: int | None = None
    for index, (amount, balance) in enumerate(rows, start=2):
        if balance is None:
            return "balance chain: skipped (no balance column)"
        if previous is not None and previous + amount != balance:
            raise MoneyError(
                f"{path.name} line {index}: balance chain broken — "
                f"expected {previous + amount:,}, file says {balance:,}. "
                "A row is likely missing or mistyped; the file was not imported."
            )
        previous = balance
    return f"balance chain: verified ({len(rows)} rows)"


def parse_amount(value: str, *, path: Path, line: int, column: str) -> int:
    """Read a yen figure, tolerating the thousands separators people type in."""
    text = (value or "").strip().replace(",", "").replace("¥", "").replace("円", "")
    if not text:
        return 0
    try:
        return int(text)
    except ValueError as exc:
        raise MoneyError(f"{path.name} line {line}: {column} is not a number: {value!r}") from exc
