"""Deciding which lines move money rather than spend it.

Moving cash between your own accounts is not income and not spending, but a
statement records it exactly like both. Leaving it in flips the sign of a whole
month's result whenever a large transfer happens, so this has to be right
before any report is worth reading.

Two mechanisms, because neither alone is enough:

* pairing — the transfer shows up in both statements, so a matching pair of
  opposite amounts a day or two apart identifies it with no configuration.
* rules — the other side is an account that is not imported (a brokerage, a
  time deposit), so only one line exists and a pattern is the only handle.

Pairing is deliberately not assumed to always succeed: whichever transfers it
cannot match are surfaced for review rather than quietly treated as spending.
"""
from __future__ import annotations

from datetime import date

from .models import Transaction
from .normalize import counterparty_key

MAX_PAIR_DAYS = 2


def _as_date(value: str) -> date:
    return date(int(value[:4]), int(value[5:7]), int(value[8:10]))


def apply_transfer_rules(transactions: list[Transaction], rules) -> list[Transaction]:
    """Flag transfers that can only be recognized by who the counterparty is.

    The flag is recomputed from the rules rather than added to whatever was
    stored, so deleting a rule actually takes effect. Carrying the old value
    forward would make the store remember decisions the rules no longer make.
    """
    result = []
    for transaction in transactions:
        is_transfer = any(
            matcher.search(transaction.desc, transaction.desc_key)
            for matcher in rules.transfer_patterns
        )
        if not is_transfer:
            # Matched against the counterparty portion only. Your own name also
            # appears on every payment you send, as the requester, so searching
            # the whole line would file rent as an internal transfer and drop it
            # out of spending entirely.
            counterparty = counterparty_key(transaction.desc_key)
            is_transfer = any(name and name in counterparty for name in rules.self_names)
        result.append(transaction.with_(is_transfer=is_transfer))
    return result


def pair_cross_account(
    transactions: list[Transaction], *, max_days: int = MAX_PAIR_DAYS
) -> list[Transaction]:
    """Match outgoing and incoming halves of the same transfer across accounts.

    Runs over the whole store on every import rather than only over new rows,
    because the other side of a transfer is often imported later — the moment
    the second account arrives, transfers already stored stop counting as
    spending.
    """
    by_id = {t.id: t for t in transactions}
    outgoing = sorted((t for t in transactions if t.amount < 0), key=lambda t: t.date)
    incoming = [t for t in transactions if t.amount > 0]
    paired: dict[str, str] = {}

    for out in outgoing:
        if out.id in paired:
            continue
        out_date = _as_date(out.date)
        best: Transaction | None = None
        best_gap = max_days + 1
        for candidate in incoming:
            if candidate.id in paired or candidate.account == out.account:
                continue
            if candidate.amount != -out.amount:
                continue
            gap = abs((_as_date(candidate.date) - out_date).days)
            # Same-day matches win; a tie keeps the earlier candidate, which is
            # the one the statements list first.
            if gap <= max_days and gap < best_gap:
                best, best_gap = candidate, gap
        if best is not None:
            paired[out.id] = best.id
            paired[best.id] = out.id

    return [
        by_id[t.id].with_(is_transfer=True, transfer_peer=paired[t.id])
        if t.id in paired
        else t.with_(transfer_peer=None)
        for t in transactions
    ]


def unpaired_transfer_candidates(transactions: list[Transaction]) -> list[Transaction]:
    """Transfers a rule caught but pairing did not — worth a human's eyes.

    Either the other account has not been imported, or the money left the
    household entirely. Those two need different handling, and only a person
    can tell them apart.
    """
    return [t for t in transactions if t.is_transfer and t.transfer_peer is None]
