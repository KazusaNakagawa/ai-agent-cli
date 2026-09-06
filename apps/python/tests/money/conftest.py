"""Synthetic statements reproducing the quirks observed in real exports.

No real statement is used anywhere in the tests. Each fixture reproduces one
structural property that actually appeared in a downloaded file — separated
voiced marks, full-width forms, a signed column vs a two-column layout, the
running balance — with invented names and amounts.
"""
import pytest

from src.money.rules import Rules, load_rules, make_matcher

# CP932, CRLF, one signed amount column, and a running balance. The description
# column mixes full-width letters, a separated voiced mark (セ + ゛) and a
# full-width hyphen standing in for a long mark, all of which real exports do.
RAKUTEN_ROWS = [
    ("20260105", 300000, 1300000, "ヤマダ　タロウ"),
    ("20260127", -12000, 1288000, "ＤＦ．セ゛ンホケン"),
    ("20260127", -40000, 1248000, "ＤＦ．ＡＢＣショウカイ"),
    ("20260131", 500, 1248500, "預金利息"),
    ("20260210", -800000, 448500, "シヨウケンガイシヤ"),
]


def _rakuten_csv() -> bytes:
    header = "取引日,入出金(円),取引後残高(円),入出金内容"
    lines = [header] + [f"{d},{a},{b},{t}" for d, a, b, t in RAKUTEN_ROWS]
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


# UTF-8, separate withdrawal/deposit columns, ISO dates. Two rows share a date,
# amount and description and differ only by balance — a real statement does
# this, and it is what forces the balance into the dedup key.
MANUAL_ROWS = [
    ("2026-01-05", 300000, 0, "振込ＩＢ２　ヤマダ　タロウ", 700000),
    ("2026-01-20", 0, 250000, "給料", 950000),
    ("2026-01-25", 10000, 0, "口座振替　ＷＡＬＬＥＴ", 940000),
    ("2026-01-25", 10000, 0, "口座振替　ＷＡＬＬＥＴ", 930000),
]


def _manual_csv() -> bytes:
    header = "date,withdrawal,deposit,description,balance,memo"
    lines = [header] + [
        f"{d},{w or ''},{dep or ''},{t},{b}," for d, w, dep, t, b in MANUAL_ROWS
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.fixture
def rakuten_csv(tmp_path):
    path = tmp_path / "RB-torihikimeisai.csv"
    path.write_bytes(_rakuten_csv())
    return path


@pytest.fixture
def manual_csv(tmp_path):
    path = tmp_path / "mufg_2026-01.csv"
    path.write_bytes(_manual_csv())
    return path


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "store" / "transactions.jsonl"


@pytest.fixture
def rules():
    """The rules a user would write for these fixtures."""
    return Rules(
        accounts={"rakuten_bank": "楽天銀行", "mufg": "三菱UFJ銀行"},
        self_names=["ヤマダタロウ"],
        transfer_patterns=[make_matcher("シヨウケンガイシヤ", where="test")],
        categories=load_rules(None).categories,
    )
