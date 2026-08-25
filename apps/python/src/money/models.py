"""Transaction record and the domain error the CLI turns into an exit.

Data shapes only. Parsing lives in ``parsers``, persistence in ``store``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

OUTPUT_DIR = Path(__file__).parents[2] / "output" / "money"
STORE_PATH = OUTPUT_DIR / "transactions.jsonl"
RULES_PATH = Path(__file__).parents[2] / "config" / "money_rules.json"

UNCATEGORIZED = "uncategorized"


class MoneyError(Exception):
    """An input file is unreadable, damaged, or fails its own arithmetic check.

    A domain exception rather than SystemExit so this layer stays usable as a
    library; the CLI turns it into an exit with the message.
    """


class UnknownFormatError(MoneyError):
    """No parser recognizes this file.

    Separate from the other failures because it means something different: the
    file is intact, it just is not a statement this phase can read. Naming a
    file explicitly should still fail loudly, but sweeping a directory that
    also holds formats for a later phase should not stop the import.
    """


@dataclass(frozen=True)
class Transaction:
    """One line of a statement, normalized across every source format.

    ``amount`` is always signed with income positive and spending negative,
    even for sources that ship separate withdrawal/deposit columns. Every
    downstream calculation depends on that, so the per-source difference is
    confined to the parsers.
    """

    id: str
    date: str  # ISO YYYY-MM-DD
    account: str
    amount: int  # JPY, income positive / spending negative
    desc_raw: str  # untouched source text; needed when a rule has to be fixed
    desc: str  # normalized, for display
    desc_key: str  # folded, for rule matching and recurrence grouping
    balance: int | None = None
    category: str = UNCATEGORIZED
    is_transfer: bool = False
    transfer_peer: str | None = None
    source_file: str = ""

    @property
    def month(self) -> str:
        return self.date[:7]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        # Unknown keys are dropped rather than raising: an older store written
        # before a field was removed should still load.
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in fields})

    def with_(self, **changes) -> "Transaction":
        return replace(self, **changes)
