"""Hand-maintained statement format, for accounts that export nothing usable.

Header: ``date,withdrawal,deposit,description,balance,memo``

Some banks only show a statement on screen. Transcribing one is a first-class
import path rather than a workaround, because the balance column makes the
transcription checkable: if a row was missed or a figure mistyped, the chain
check in ``base`` refuses the file.

The account is taken from the filename up to the first ``_`` or ``-``
(``mufg_2025-07_2026-07.csv`` -> ``mufg``); the format has no account column
because one file always covers one account. The import summary prints the
account it derived, so a typo in a filename is visible rather than silently
creating a second account.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from ..models import MoneyError, Transaction
from .base import (
    ParseResult,
    build_transaction,
    parse_amount,
    verify_balance_chain,
    verify_calendar_date,
)

NAME = "manual"

COLUMNS = ("date", "withdrawal", "deposit", "description", "balance")
_ACCOUNT_FROM_STEM = re.compile(r"^[^_\-]+")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def sniff(text: str) -> bool:
    header = text.splitlines()[0] if text else ""
    names = {name.strip() for name in header.split(",")}
    return all(column in names for column in COLUMNS)


def account_for(path: Path) -> str:
    match = _ACCOUNT_FROM_STEM.match(path.stem)
    if not match:
        raise MoneyError(
            f"{path.name}: cannot tell which account this is. Name the file after the "
            "account, e.g. mufg_2025-07.csv"
        )
    return match.group(0).lower()


def parse(path: Path, text: str) -> ParseResult:
    account = account_for(path)
    reader = csv.DictReader(io.StringIO(text))
    transactions: list[Transaction] = []
    chain: list[tuple[int, int | None]] = []

    for line, row in enumerate(reader, start=2):
        # A row with fewer fields than the header leaves the trailing columns
        # as None. Caught here rather than downstream because the damage is
        # quiet: a missing balance would merely turn the chain check off, and a
        # missing description would surface as an AttributeError from
        # normalization instead of a line number.
        missing = [column for column in COLUMNS if row.get(column) is None]
        if missing:
            raise MoneyError(
                f"{path.name} line {line}: row has fewer columns than the header — "
                f"missing {', '.join(missing)}"
            )

        date = row["date"].strip()
        if not _ISO_DATE.match(date):
            raise MoneyError(f"{path.name} line {line}: expected a YYYY-MM-DD date, got {date!r}")
        verify_calendar_date(date, path=path, line=line)

        description = row["description"].strip()
        if not description:
            raise MoneyError(
                f"{path.name} line {line}: description is empty, so the row cannot be "
                "attributed to a counterparty"
            )

        withdrawal = parse_amount(row["withdrawal"], path=path, line=line, column="withdrawal")
        deposit = parse_amount(row["deposit"], path=path, line=line, column="deposit")
        if withdrawal and deposit:
            raise MoneyError(
                f"{path.name} line {line}: a row cannot be both a withdrawal and a deposit"
            )
        # Two columns collapse into one signed amount here so nothing downstream
        # has to know this format had them separate.
        amount = deposit - withdrawal

        # A blank balance is refused rather than tolerated: the running balance
        # is the only thing that proves a transcribed statement is complete, and
        # one empty cell would switch that check off for the whole file.
        raw_balance = row["balance"].strip()
        if not raw_balance:
            raise MoneyError(
                f"{path.name} line {line}: balance is empty, and the balance chain is "
                "what makes a transcribed statement checkable — fill it in"
            )
        balance = parse_amount(raw_balance, path=path, line=line, column="balance")
        transactions.append(
            build_transaction(
                account=account,
                date=date,
                amount=amount,
                # The untouched cell, not the stripped copy used for the check
                # above: desc_raw is the source text, and folding whitespace
                # into it would change the ids of rows already stored.
                desc_raw=row["description"],
                balance=balance,
                source_file=path.name,
            )
        )
        chain.append((amount, balance))

    return ParseResult(
        path=path,
        parser=NAME,
        account=account,
        transactions=transactions,
        checks=[verify_balance_chain(chain, path=path)],
    )
