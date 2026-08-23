"""Monthly cash-flow reporting.

Transfers are excluded everywhere: they are the difference between a report
that reflects the household and one that reports moving your own money as if it
were spent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import UNCATEGORIZED, Transaction
from .rules import Rules


@dataclass
class MonthSummary:
    month: str
    income: int = 0
    expense: int = 0  # positive figure
    transfers_excluded: int = 0
    uncategorized_rows: int = 0
    categories: dict[str, int] = field(default_factory=dict)

    @property
    def net(self) -> int:
        return self.income - self.expense

    @property
    def savings_rate(self) -> float | None:
        """Share of income kept. Undefined in a month with no income."""
        if self.income <= 0:
            return None
        return self.net / self.income


def months_covered(transactions: list[Transaction]) -> list[str]:
    return sorted({t.month for t in transactions})


def summarize_month(transactions: list[Transaction], month: str) -> MonthSummary:
    summary = MonthSummary(month=month)
    for transaction in transactions:
        if transaction.month != month:
            continue
        if transaction.is_transfer:
            summary.transfers_excluded += 1
            continue
        if transaction.amount >= 0:
            summary.income += transaction.amount
        else:
            summary.expense += -transaction.amount
        if transaction.category == UNCATEGORIZED:
            summary.uncategorized_rows += 1
        summary.categories[transaction.category] = (
            summary.categories.get(transaction.category, 0) + transaction.amount
        )
    return summary


def category_labels(rules: Rules) -> dict[str, str]:
    """Display name per category, from the rules that share that category.

    Rules that share a category are expected to share a label. When they
    disagree the category key is shown instead of picking one of them — a row
    totalling several counterparties under one of their names reads as though
    that single counterparty cost the lot.
    """
    seen: dict[str, set[str]] = {}
    for rule in rules.categories:
        if rule.label:
            seen.setdefault(rule.category, set()).add(rule.label)
    return {category: next(iter(labels)) for category, labels in seen.items() if len(labels) == 1}


def _yen(value: int) -> str:
    return f"{value:,} 円"


def _rate(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _delta(current: int, previous: int | None) -> str:
    if previous is None:
        return "—"
    return f"{current - previous:+,}"


def _rate_delta(current: float | None, previous: float | None) -> str:
    """Change in savings rate, in points — a ratio's delta is not a ratio."""
    if current is None or previous is None:
        return "—"
    return f"{(current - previous) * 100:+.1f}pt"


def render_month(
    summary: MonthSummary, rules: Rules, *, previous: MonthSummary | None = None
) -> str:
    lines = [f"# 家計サマリー {summary.month}", "", "## 収支", "", "| | 金額 | 前月比 |", "|---|---|---|"]
    lines.append(f"| 収入 | {_yen(summary.income)} | {_delta(summary.income, previous.income if previous else None)} |")
    lines.append(f"| 支出 | {_yen(summary.expense)} | {_delta(summary.expense, previous.expense if previous else None)} |")
    lines.append(f"| 収支 | {_yen(summary.net)} | {_delta(summary.net, previous.net if previous else None)} |")
    lines.append(
        f"| 貯蓄率 | {_rate(summary.savings_rate)} | "
        f"{_rate_delta(summary.savings_rate, previous.savings_rate if previous else None)} |"
    )
    lines += ["", f"振替として除外: {summary.transfers_excluded} 件", "", "## カテゴリ別", ""]

    if summary.categories:
        labels = category_labels(rules)
        lines += ["| カテゴリ | 金額 |", "|---|---|"]
        for category, amount in sorted(summary.categories.items(), key=lambda kv: kv[1]):
            lines.append(f"| {labels.get(category, category)} | {_yen(amount)} |")
    else:
        lines.append("この月の明細はありません。")

    if summary.uncategorized_rows:
        lines += [
            "",
            f"> 未分類が {summary.uncategorized_rows} 件あります。"
            " `bin/money.sh review` で確認し、`config/money_rules.json` にルールを足してください。",
        ]
    return "\n".join(lines) + "\n"


def render_range(transactions: list[Transaction], months: list[str]) -> str:
    """One row per month, so a trend is visible without opening each report."""
    lines = [
        f"# 家計サマリー {months[0]} 〜 {months[-1]}",
        "",
        "| 月 | 収入 | 支出 | 収支 | 貯蓄率 | 振替除外 |",
        "|---|---|---|---|---|---|",
    ]
    totals = MonthSummary(month="合計")
    for month in months:
        summary = summarize_month(transactions, month)
        totals.income += summary.income
        totals.expense += summary.expense
        totals.transfers_excluded += summary.transfers_excluded
        lines.append(
            f"| {month} | {summary.income:,} | {summary.expense:,} | {summary.net:,} | "
            f"{_rate(summary.savings_rate)} | {summary.transfers_excluded} |"
        )
    lines.append(
        f"| **合計** | **{totals.income:,}** | **{totals.expense:,}** | **{totals.net:,}** | "
        f"**{_rate(totals.savings_rate)}** | **{totals.transfers_excluded}** |"
    )
    average = totals.expense // len(months) if months else 0
    lines += ["", f"平均月支出: {_yen(average)}（{len(months)} ヶ月）"]
    return "\n".join(lines) + "\n"
