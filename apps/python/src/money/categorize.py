"""Rule-based categorization. No LLM involved at this stage.

Rules are matched against both the folded key and the readable description, so
a rule can be written either the way the world spells a name or the way the
bank does.
"""
from __future__ import annotations

from .models import UNCATEGORIZED, Transaction
from .rules import CategoryRule, Rules


def match_rule(transaction: Transaction, rules: Rules) -> CategoryRule | None:
    for rule in rules.categories:
        if rule.matcher.search(transaction.desc, transaction.desc_key):
            return rule
    return None


def categorize(transactions: list[Transaction], rules: Rules) -> list[Transaction]:
    """Assign a category to every transaction, leaving misses visible."""
    result = []
    for transaction in transactions:
        rule = match_rule(transaction, rules)
        result.append(transaction.with_(category=rule.category if rule else UNCATEGORIZED))
    return result


def uncategorized(transactions: list[Transaction]) -> list[Transaction]:
    return [t for t in transactions if t.category == UNCATEGORIZED and not t.is_transfer]
