"""Build money-job.json for money.mjs from the local household ledger.

One row per distinct description (desc_key): rule-categorized rows carry the
rule's category as the expected answer, uncategorized rows carry none and are
left for a human to judge. Only the redacted description, direction and amount
are kept — no dates, accounts or rule notes leave this machine.

Usage (from repo root):
    apps/python/.venv/bin/python scripts/jev/make_money_job.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps/python"))

from src.money import categorize as C  # noqa: E402
from src.money import rules as R  # noqa: E402
from src.money import store  # noqa: E402
from src.money.models import RULES_PATH, STORE_PATH, UNCATEGORIZED  # noqa: E402

OUT = Path(__file__).resolve().parent / "money-job.json"

# Bank transfer descriptions embed the sender's name, branch, account number
# and a reference number. None of it helps classification, all of it is
# personal, so it is stripped before anything is written for an external call.
_REDACTIONS = (
    (re.compile(r"[(（]依頼人名[:：][^)）]*[)）]"), ""),
    (re.compile(r"\S+支店"), ""),
    (re.compile(r"\d{4,}"), "####"),
)


def redact(desc: str) -> str:
    for pattern, repl in _REDACTIONS:
        desc = pattern.sub(repl, desc)
    return re.sub(r"\s+", " ", desc).strip()


def main() -> None:
    if not STORE_PATH.exists():
        sys.exit(f"missing {STORE_PATH}: import statements with bin/money.sh first")
    rules = R.load_rules(RULES_PATH)
    rows = [t for t in C.categorize(store.load(STORE_PATH), rules) if not t.is_transfer]

    seen: set[str] = set()
    items = []
    for t in rows:
        if t.desc_key in seen:
            continue
        seen.add(t.desc_key)
        items.append({
            "desc": redact(t.desc),
            "direction": "入金" if t.amount > 0 else "出金",
            "amount": abs(t.amount),
            "expected": None if t.category == UNCATEGORIZED else t.category,
        })
    if not items:
        sys.exit("no non-transfer transactions in the ledger")

    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    labeled = sum(i["expected"] is not None for i in items)
    print(f"{len(items)} distinct descriptions ({labeled} labeled, {len(items) - labeled} uncategorized) -> {OUT}")


if __name__ == "__main__":
    main()
