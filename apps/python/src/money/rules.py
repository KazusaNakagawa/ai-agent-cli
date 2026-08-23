"""User-editable rules, layered on top of safe built-in defaults.

The package works with no config file at all: the built-ins cover the handful of
counterparties every statement has (salary, bonus, interest). Anything personal
— which names are your own accounts, which counterparty is which category —
lives in ``config/money_rules.json``, which is never committed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import MoneyError
from .normalize import match_key


# A pattern with none of these is plain text, which means it can safely be run
# through the same folding as a description. Folding a real regex would corrupt
# it (upper() alone turns "\d" into "\D"), so it is only done for literals.
_REGEX_META = set(".^$*+?{}[]()|\\")


@dataclass(frozen=True)
class Matcher:
    """A user-written pattern, tried against every spelling of a description.

    The whole point of the folded match key is that a rule can be written the
    way the world spells a name while the bank writes it with full-size kana and
    no long marks. That only works if the pattern is folded the same way, so a
    literal pattern gets a folded twin here.
    """

    source: str
    raw: re.Pattern
    folded: re.Pattern | None = None

    def search(self, desc: str, desc_key: str) -> bool:
        if self.raw.search(desc) or self.raw.search(desc_key):
            return True
        return bool(self.folded is not None and self.folded.search(desc_key))


@dataclass(frozen=True)
class CategoryRule:
    matcher: Matcher
    category: str
    label: str = ""
    fixed_cost: bool = False
    note: str = ""


# Deliberately tiny. Interest is matched before bonus because a bank can pay
# "ボーナス金利利息" — bonus-rate interest — which is income from interest, not a
# salary bonus, and the first matching rule wins.
BUILTIN_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    (r"利息|金利", "income_interest", "利息"),
    (r"給料|給与", "income_salary", "給与"),
    (r"賞与", "income_bonus", "賞与"),
)


@dataclass
class Rules:
    accounts: dict[str, str] = field(default_factory=dict)
    self_names: list[str] = field(default_factory=list)
    transfer_patterns: list[Matcher] = field(default_factory=list)
    categories: list[CategoryRule] = field(default_factory=list)

    def account_label(self, account: str) -> str:
        return self.accounts.get(account, account)


def _builtin_rules() -> list[CategoryRule]:
    return [
        CategoryRule(matcher=make_matcher(p, where="builtin"), category=c, label=label)
        for p, c, label in BUILTIN_CATEGORIES
    ]


def make_matcher(pattern: str, *, where: str) -> Matcher:
    try:
        raw = re.compile(pattern)
    except re.error as exc:
        raise MoneyError(f"{where}: invalid regular expression {pattern!r} ({exc})") from exc

    folded = None
    if not (_REGEX_META & set(pattern)):
        key = match_key(pattern)
        if key and key != pattern:
            folded = re.compile(re.escape(key))
    return Matcher(source=pattern, raw=raw, folded=folded)


def load_rules(path: Path | None) -> Rules:
    """Read the rules file if it exists; otherwise return the built-ins alone."""
    rules = Rules(categories=_builtin_rules())
    if path is None or not path.exists():
        return rules

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MoneyError(f"{path}: is not valid JSON ({exc})") from exc

    # Keys beginning with "_" are documentation the example file carries, so a
    # copied-and-edited config never turns its own comments into rules.
    for key, value in (data.get("accounts") or {}).items():
        if key.startswith("_"):
            continue
        rules.accounts[key] = value.get("label", key) if isinstance(value, dict) else str(value)

    # Stored folded so a name written the natural way still matches whatever
    # spelling the bank used.
    rules.self_names = [
        match_key(name) for name in data.get("self_names") or [] if not name.startswith("_")
    ]

    rules.transfer_patterns = [
        make_matcher(p, where=f"{path.name} transfer_patterns")
        for p in data.get("transfer_patterns") or []
        if not p.startswith("_")
    ]

    # User rules are evaluated before the built-ins so a specific counterparty
    # can override a generic keyword.
    user_rules = []
    for entry in data.get("categories") or []:
        if "pattern" not in entry or "category" not in entry:
            raise MoneyError(f"{path.name}: every category rule needs 'pattern' and 'category'")
        user_rules.append(
            CategoryRule(
                matcher=make_matcher(entry["pattern"], where=f"{path.name} categories"),
                category=entry["category"],
                label=entry.get("label", ""),
                fixed_cost=bool(entry.get("fixed_cost", False)),
                note=entry.get("note", ""),
            )
        )
    rules.categories = user_rules + rules.categories
    return rules
