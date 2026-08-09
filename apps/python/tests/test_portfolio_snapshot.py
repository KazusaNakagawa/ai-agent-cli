import json
from unittest.mock import patch

import pytest

from src.fetcher.stocks import StockQuote
from src.portfolio_snapshot import (
    Holdings,
    Position,
    Snapshot,
    build_snapshot,
    fetch_quotes,
    load_holdings,
    render_snapshot,
    value_positions,
)

FX = 150.0


def _quote(ticker, price, currency="USD"):
    return StockQuote(
        ticker=ticker,
        last_price=price,
        previous_close=price,
        change_pct=0.0,
        currency=currency,
    )


def _snapshot(positions, *, cash_jpy=0.0, cash_usd=0.0, quotes=None, nisa=None):
    """Build a Snapshot from positions and canned quotes (no network)."""
    holdings = Holdings(
        as_of="2026-08-09",
        positions=positions,
        cash_jpy=cash_jpy,
        cash_usd=cash_usd,
        nisa_growth_remaining_jpy=nisa,
    )
    return Snapshot(
        holdings=holdings,
        valued=value_positions(positions, quotes or {}, FX),
        fx=FX,
    )


class TestHoldingsParsing:
    def test_reads_positions_cash_and_metadata(self, tmp_path):
        path = tmp_path / "holdings.json"
        path.write_text(
            json.dumps(
                {
                    "as_of": "2026-08-09",
                    "source": "brokerage export",
                    "cash": {"JPY": 1000, "USD": 20},
                    "nisa_growth_remaining_jpy": 969000,
                    "positions": [
                        {"ticker": "MSFT", "shares": 10, "avg_cost": 300, "account": "特定"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        holdings = load_holdings(path)
        assert holdings.as_of == "2026-08-09"
        assert holdings.cash_jpy == 1000
        assert holdings.cash_usd == 20
        assert holdings.nisa_growth_remaining_jpy == 969000
        assert holdings.positions[0] == Position(
            ticker="MSFT", shares=10, avg_cost=300, account="特定"
        )

    def test_missing_cash_section_is_zero_not_an_error(self):
        holdings = Holdings.from_dict({"as_of": "2026-08-09", "positions": []})
        assert (holdings.cash_jpy, holdings.cash_usd) == (0.0, 0.0)

    def test_unknown_keys_are_ignored(self):
        # The example file carries "_comment" keys for the reader.
        position = Position.from_dict({"ticker": "MSFT", "_comment": "note"})
        assert position.ticker == "MSFT"

    def test_absent_file_exits_with_a_pointer_to_the_example(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            load_holdings(tmp_path / "nope.json")
        assert "holdings.json.example" in str(excinfo.value)


class TestQuoteFetching:
    def test_one_fetch_per_ticker_even_when_held_in_two_accounts(self):
        positions = [
            Position(ticker="PLTR", shares=100, account="特定"),
            Position(ticker="PLTR", shares=4, account="NISA"),
            Position(ticker="MSFT", shares=10),
        ]
        with patch("src.portfolio_snapshot.fetch_stock_quotes", return_value={}) as fetch:
            fetch_quotes(positions)
        assert fetch.call_args.args[0] == ["PLTR", "MSFT"]

    def test_manual_positions_are_never_quoted(self):
        positions = [Position(ticker="楽天VTI", manual_value_jpy=1000)]
        with patch("src.portfolio_snapshot.fetch_stock_quotes") as fetch:
            assert fetch_quotes(positions) == {}
        fetch.assert_not_called()


class TestValuation:
    def test_usd_position_is_converted_at_the_fx_rate(self):
        valued = value_positions(
            [Position(ticker="MSFT", shares=10, avg_cost=300)],
            {"MSFT": _quote("MSFT", 500)},
            FX,
        )[0]
        assert valued.value_jpy == 10 * 500 * FX
        assert valued.cost_jpy == 10 * 300 * FX
        assert valued.pnl_pct == pytest.approx(66.67, abs=0.01)

    def test_jpy_listed_position_is_not_converted(self):
        valued = value_positions(
            [Position(ticker="4676.T", shares=100, avg_cost=1970.5)],
            {"4676.T": _quote("4676.T", 4054, currency="JPY")},
            FX,
        )[0]
        assert valued.value_jpy == 100 * 4054

    def test_manual_position_uses_its_supplied_yen_figures(self):
        valued = value_positions(
            [Position(ticker="楽天VTI", manual_value_jpy=1994755, manual_cost_jpy=799999)],
            {},
            FX,
        )[0]
        assert valued.value_jpy == 1994755
        assert valued.is_manual

    def test_position_without_shares_is_left_unvalued(self):
        valued = value_positions(
            [Position(ticker="MSFT")], {"MSFT": _quote("MSFT", 500)}, FX
        )[0]
        assert valued.value_jpy is None

    def test_failed_quote_is_left_unvalued_and_keeps_the_error(self):
        quote = StockQuote(ticker="MSFT", error="Stock fetch error (boom)")
        valued = value_positions([Position(ticker="MSFT", shares=10)], {"MSFT": quote}, FX)[0]
        assert valued.value_jpy is None
        assert valued.error == "Stock fetch error (boom)"


class TestFxExposure:
    """Listing currency alone understates FX risk, so exposure is look-through."""

    def test_defaults_to_full_exposure_for_usd_and_none_for_jpy(self):
        valued = value_positions(
            [
                Position(ticker="MSFT", shares=1),
                Position(ticker="4676.T", shares=1),
            ],
            {"MSFT": _quote("MSFT", 100), "4676.T": _quote("4676.T", 100, currency="JPY")},
            FX,
        )
        assert valued[0].fx_exposed_jpy == 100 * FX
        assert valued[1].fx_exposed_jpy == 0.0

    def test_explicit_ratio_wins_for_a_yen_quoted_world_index(self):
        valued = value_positions(
            [Position(ticker="1554.T", shares=100, fx_exposure=0.95)],
            {"1554.T": _quote("1554.T", 1000, currency="JPY")},
            FX,
        )[0]
        assert valued.fx_exposed_jpy == pytest.approx(100 * 1000 * 0.95)

    def test_usd_cash_counts_as_foreign_exposure(self):
        s = _snapshot([], cash_jpy=1000, cash_usd=10)
        assert s.foreign_jpy == 10 * FX


class TestTotals:
    def test_weights_are_taken_over_equity_plus_cash(self):
        s = _snapshot(
            [Position(ticker="MSFT", shares=10)],
            cash_jpy=1500 * FX,
            quotes={"MSFT": _quote("MSFT", 1500)},
        )
        assert s.equity_jpy == 1500 * 10 * FX
        assert s.total_jpy == 1500 * 11 * FX
        assert s.weight(s.cash_jpy) == pytest.approx(100 / 11)

    def test_by_ticker_sums_the_same_name_across_accounts(self):
        s = _snapshot(
            [
                Position(ticker="PLTR", shares=100, account="特定"),
                Position(ticker="PLTR", shares=4, account="NISA"),
            ],
            quotes={"PLTR": _quote("PLTR", 100)},
        )
        assert s.by_ticker()["PLTR"] == 104 * 100 * FX
        assert s.account_count("PLTR") == 2

    def test_unvalued_tickers_are_reported_rather_than_silently_dropped(self):
        s = _snapshot([Position(ticker="MSFT")], quotes={"MSFT": _quote("MSFT", 500)})
        assert s.unvalued_tickers == ["MSFT"]


class TestRules:
    def _rules(self, s: Snapshot) -> str:
        return render_snapshot(s).split("## ルール判定")[1]

    def test_single_name_concentration_is_judged_on_the_across_account_total(self):
        # Regression: judging one row alone put PLTR under the threshold while
        # the two accounts together were well over it.
        s = _snapshot(
            [
                Position(ticker="PLTR", shares=90, account="特定"),
                Position(ticker="PLTR", shares=10, account="NISA"),
                Position(ticker="MSFT", shares=400, account="特定"),
            ],
            quotes={"PLTR": _quote("PLTR", 100), "MSFT": _quote("MSFT", 100)},
        )
        rules = self._rules(s)
        assert "PLTR 比率 **20.0%**" in rules
        assert "見送り・比率維持" in rules

    def test_index_funds_are_exempt_from_the_single_name_rule(self):
        s = _snapshot(
            [Position(ticker="楽天VTI", bucket="index", manual_value_jpy=1_000_000)],
        )
        assert "楽天VTI 比率" not in self._rules(s)

    def test_high_risk_sleeve_flags_both_the_bucket_and_the_single_name(self):
        s = _snapshot(
            [
                Position(ticker="MU", shares=1, bucket="high_risk"),
                Position(ticker="MSFT", shares=4),
            ],
            quotes={"MU": _quote("MU", 100), "MSFT": _quote("MSFT", 100)},
        )
        rules = self._rules(s)
        assert "高リスク枠 **20.0%**（ガイド 15% 以内） → 超過" in rules
        assert "MU 20.0%（1銘柄 5% 以内） → 超過" in rules

    def test_high_risk_sleeve_within_the_guide_passes(self):
        s = _snapshot(
            [
                Position(ticker="MU", shares=1, bucket="high_risk"),
                Position(ticker="MSFT", shares=99),
            ],
            quotes={"MU": _quote("MU", 100), "MSFT": _quote("MSFT", 100)},
        )
        assert "高リスク枠 **1.0%**（ガイド 15% 以内） → OK" in self._rules(s)

    def test_empty_holdings_say_what_to_do_instead_of_dividing_by_zero(self):
        assert "holdings.json を埋めてください" in self._rules(_snapshot([]))


class TestRender:
    def test_sections_and_scenarios_are_present(self):
        s = _snapshot(
            [Position(ticker="MSFT", shares=10, avg_cost=300, name="マイクロソフト")],
            cash_jpy=10_000,
            quotes={"MSFT": _quote("MSFT", 500)},
        )
        text = render_snapshot(s)
        for heading in ("## 保有一覧", "## 通貨エクスポージャー", "## 区分別の集中度", "## ルール判定"):
            assert heading in text
        assert "USD/JPY **140**" in text
        assert "マイクロソフト" in text

    def test_manual_rows_are_labelled_and_sourced(self):
        holdings = Holdings(
            as_of="2026-08-09",
            positions=[Position(ticker="楽天VTI", bucket="index", manual_value_jpy=1000)],
            source="brokerage export 2026-07-29",
        )
        s = Snapshot(
            holdings=holdings,
            valued=value_positions(holdings.positions, {}, FX),
            fx=FX,
        )
        text = render_snapshot(s)
        assert "手入力" in text
        assert "brokerage export 2026-07-29" in text

    def test_ticker_totals_table_appears_only_for_split_holdings(self):
        single = _snapshot(
            [Position(ticker="MSFT", shares=10)], quotes={"MSFT": _quote("MSFT", 500)}
        )
        assert "## 口座をまたぐ銘柄の合計" not in render_snapshot(single)

        split = _snapshot(
            [
                Position(ticker="MSFT", shares=10, account="特定"),
                Position(ticker="MSFT", shares=1, account="NISA"),
            ],
            quotes={"MSFT": _quote("MSFT", 500)},
        )
        assert "## 口座をまたぐ銘柄の合計" in render_snapshot(split)


class TestBuildSnapshot:
    def test_fetches_fx_and_quotes_once(self):
        holdings = Holdings(as_of="2026-08-09", positions=[Position(ticker="MSFT", shares=2)])
        with patch(
            "src.portfolio_snapshot.fetch_stock_quotes",
            return_value={"MSFT": _quote("MSFT", 500)},
        ):
            s = build_snapshot(holdings, fx=FX)
        assert s.equity_jpy == 2 * 500 * FX
