"""Rakuten Bank transaction statement (CP932, CRLF, one signed amount column).

Header: ``取引日,入出金(円),取引後残高(円),入出金内容``
Dates arrive as ``YYYYMMDD`` and the amount column is already signed, so the
only real work is the date shape and the balance check.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ..models import MoneyError, Transaction
from .base import (
    ParseResult,
    build_transaction,
    parse_amount,
    verify_balance_chain,
    verify_calendar_date,
)

NAME = "rakuten_bank"
ACCOUNT = "rakuten_bank"

DATE_COLUMN = "取引日"
AMOUNT_COLUMN = "入出金(円)"
BALANCE_COLUMN = "取引後残高(円)"
DESC_COLUMN = "入出金内容"
COLUMNS = (DATE_COLUMN, AMOUNT_COLUMN, BALANCE_COLUMN, DESC_COLUMN)


def sniff(text: str) -> bool:
    header = text.splitlines()[0] if text else ""
    return all(column in header for column in COLUMNS)


def _iso_date(value: str, *, path: Path, line: int) -> str:
    digits = value.strip()
    if len(digits) != 8 or not digits.isdigit():
        raise MoneyError(f"{path.name} line {line}: expected a YYYYMMDD date, got {value!r}")
    # Eight digits is only the shape; 20260230 has it and is not a day.
    return verify_calendar_date(
        f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}", path=path, line=line
    )


def parse(path: Path, text: str) -> ParseResult:
    reader = csv.DictReader(io.StringIO(text))
    transactions: list[Transaction] = []
    chain: list[tuple[int, int | None]] = []

    for line, row in enumerate(reader, start=2):
        # A truncated row leaves trailing columns as None, which would reach
        # normalization as an AttributeError with no line number attached.
        missing = [column for column in COLUMNS if row.get(column) is None]
        if missing:
            raise MoneyError(
                f"{path.name} line {line}: row has fewer columns than the header — "
                f"missing {', '.join(missing)}"
            )
        amount = parse_amount(row[AMOUNT_COLUMN], path=path, line=line, column=AMOUNT_COLUMN)
        balance = parse_amount(row[BALANCE_COLUMN], path=path, line=line, column=BALANCE_COLUMN)
        transactions.append(
            build_transaction(
                account=ACCOUNT,
                date=_iso_date(row[DATE_COLUMN], path=path, line=line),
                amount=amount,
                desc_raw=row[DESC_COLUMN],
                balance=balance,
                source_file=path.name,
            )
        )
        chain.append((amount, balance))

    return ParseResult(
        path=path,
        parser=NAME,
        account=ACCOUNT,
        transactions=transactions,
        checks=[verify_balance_chain(chain, path=path)],
    )
