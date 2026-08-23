"""JSONL transaction store — one line per transaction, rewritten in full.

Deliberately not SQLite: every other store in this repo is file-based, a
household's ledger is a few thousand rows a year, and a text file stays
readable and repairable by hand when something goes wrong. The schema is
already fixed, so moving to SQLite later is mechanical if it is ever needed.

The file is rewritten rather than appended because transfer pairing can change
rows that were stored earlier — importing a second account retroactively turns
already-stored lines into transfers.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import Transaction


def load(path: Path) -> list[Transaction]:
    if not path.exists():
        return []
    transactions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            transactions.append(Transaction.from_dict(json.loads(line)))
    return transactions


def save(path: Path, transactions: list[Transaction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(transactions, key=lambda t: (t.date, t.account, t.id))
    payload = "".join(
        json.dumps(t.to_dict(), ensure_ascii=False) + "\n" for t in ordered
    )
    # Written to a sibling temporary file and moved into place, so the store is
    # either the old ledger or the new one and never a truncated mix of the
    # two. Writing over the file directly would leave it half-written if the
    # process died mid-write, and this is the only copy of the data.
    # os.replace is atomic within a filesystem, hence the same directory.
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def merge(existing: list[Transaction], incoming: list[Transaction]) -> tuple[list[Transaction], int, int]:
    """Add only transactions not already stored. Returns (merged, added, duplicates).

    Identity is the content hash, so re-importing the same file — or a longer
    export that overlaps one already imported — adds nothing.
    """
    by_id = {t.id: t for t in existing}
    added = 0
    duplicates = 0
    for transaction in incoming:
        if transaction.id in by_id:
            duplicates += 1
            continue
        by_id[transaction.id] = transaction
        added += 1
    return list(by_id.values()), added, duplicates
