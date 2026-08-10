import json
import logging
import re
from unittest.mock import patch

import pytest

from src.fetcher.stocks import StockQuote
from src.portfolio_snapshot import (
    EXAMPLE_PATH,
    FX_FALLBACK,
    FX_SCENARIOS,
    Holdings,
    HoldingsError,
    Position,
    Snapshot,
    build_snapshot,
    fetch_fx,
    fetch_quotes,
    load_holdings,
    main,
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

    def test_absent_file_names_both_the_missing_path_and_the_template(self, tmp_path):
        # With --holdings the missing file is not the default one, so the
        # message has to name the path actually looked for.
        missing = tmp_path / "nope.json"
        with pytest.raises(HoldingsError) as excinfo:
            load_holdings(missing)
        message = str(excinfo.value)
        assert str(missing) in message
        assert str(EXAMPLE_PATH) in message
        assert EXAMPLE_PATH.exists(), "the template the message points at must be tracked"


    @pytest.mark.parametrize(
        "data, expected",
        [
            ({"cash": {"JPY": "1,000,000"}, "positions": []}, "cash.JPY"),
            ({"cash": {"USD": "abc"}, "positions": []}, "cash.USD"),
            (
                {"nisa_growth_remaining_jpy": "969,000", "positions": []},
                "nisa_growth_remaining_jpy",
            ),
            ({"positions": [{"ticker": "MSFT", "shares": "10 shares"}]}, "MSFT.shares"),
            ({"positions": [{"ticker": "MSFT", "avg_cost": "$289"}]}, "MSFT.avg_cost"),
            (
                {"positions": [{"ticker": "楽天VTI", "manual_value_jpy": "1,994,755"}]},
                "楽天VTI.manual_value_jpy",
            ),
        ],
    )
    def test_a_non_numeric_field_names_the_field_instead_of_crashing_later(
        self, data, expected
    ):
        # Valid JSON, invalid number: without this the failure surfaces as a
        # TypeError deep in the valuation with nothing pointing at the line.
        with pytest.raises(HoldingsError) as excinfo:
            Holdings.from_dict(data)
        assert expected in str(excinfo.value)

    def test_numeric_strings_are_accepted(self):
        # A quoted plain number is unambiguous, so it parses rather than errors.
        holdings = Holdings.from_dict(
            {"cash": {"JPY": "1000"}, "positions": [{"ticker": "MSFT", "shares": "10"}]}
        )
        assert holdings.cash_jpy == 1000.0
        assert holdings.positions[0].shares == 10.0

    def test_a_position_without_a_ticker_is_reported(self):
        with pytest.raises(HoldingsError) as excinfo:
            Holdings.from_dict({"positions": [{"shares": 10}]})
        assert "missing its ticker" in str(excinfo.value)

    def test_malformed_json_names_the_file_and_the_position(self, tmp_path):
        path = tmp_path / "holdings.json"
        path.write_text('{"as_of": "2026-08-09",}', encoding="utf-8")
        with pytest.raises(HoldingsError) as excinfo:
            load_holdings(path)
        message = str(excinfo.value)
        assert "not valid JSON" in message
        assert str(path) in message
        assert "line 1, column" in message


class TestQuoteFetching:
    def test_one_fetch_per_ticker_even_when_held_in_two_accounts(self):
        positions = [
            Position(ticker="PLTR", shares=100, account="特定"),
            Position(ticker="PLTR", shares=4, account="NISA"),
            Position(ticker="MSFT", shares=10),
        ]
        with patch("src.portfolio_snapshot.valuation.fetch_stock_quotes", return_value={}) as fetch:
            fetch_quotes(positions)
        assert fetch.call_args.args[0] == ["PLTR", "MSFT"]

    def test_manual_positions_are_never_quoted(self):
        positions = [Position(ticker="楽天VTI", manual_value_jpy=1000)]
        with patch("src.portfolio_snapshot.valuation.fetch_stock_quotes") as fetch:
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

    def test_a_price_of_zero_is_valued_at_zero_not_left_unknown(self):
        # A written-off holding still quotes; 0 must not read as "no price".
        valued = value_positions(
            [Position(ticker="DEAD", shares=10, avg_cost=50)], {"DEAD": _quote("DEAD", 0.0)}, FX
        )[0]
        assert valued.value_jpy == 0.0
        assert valued.pnl_pct == -100.0

    def test_zero_shares_is_valued_at_zero(self):
        valued = value_positions(
            [Position(ticker="MSFT", shares=0)], {"MSFT": _quote("MSFT", 500)}, FX
        )[0]
        assert valued.value_jpy == 0.0

    def test_failed_quote_is_left_unvalued_and_keeps_the_error(self):
        quote = StockQuote(ticker="MSFT", error="Stock fetch error (boom)")
        valued = value_positions([Position(ticker="MSFT", shares=10)], {"MSFT": quote}, FX)[0]
        assert valued.value_jpy is None
        assert valued.error == "Stock fetch error (boom)"


class TestFetchFx:
    def test_missing_usd_jpy_quote_falls_back_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            with patch("src.portfolio_snapshot.valuation.fetch_stock_quotes", return_value={}):
                assert fetch_fx() == FX_FALLBACK
        assert "USD/JPY fetch failed" in caplog.text

    def test_quote_without_a_price_falls_back_too(self, caplog):
        quote = StockQuote(ticker="JPY=X", error="Stock fetch error (boom)")
        with caplog.at_level(logging.WARNING):
            with patch(
                "src.portfolio_snapshot.valuation.fetch_stock_quotes",
                return_value={"JPY=X": quote},
            ):
                assert fetch_fx() == FX_FALLBACK
        assert "USD/JPY fetch failed" in caplog.text

    def test_a_good_quote_is_used_as_is(self):
        with patch(
            "src.portfolio_snapshot.valuation.fetch_stock_quotes",
            return_value={"JPY=X": _quote("JPY=X", 157.74, currency="JPY")},
        ):
            assert fetch_fx() == 157.74


class TestZeroValuedPositions:
    """A position worth exactly 0 is known, not unknown — it must not vanish."""

    def _zero(self):
        return _snapshot(
            [
                Position(ticker="DEAD", shares=10, bucket="ai_growth", account="特定"),
                Position(ticker="MSFT", shares=10, bucket="ai_growth", account="特定"),
            ],
            quotes={"DEAD": _quote("DEAD", 0.0), "MSFT": _quote("MSFT", 100)},
        )

    def test_it_is_not_reported_as_unvalued(self):
        assert self._zero().unvalued_tickers == []

    def test_it_appears_in_the_per_ticker_and_bucket_totals(self):
        s = self._zero()
        assert s.by_ticker()["DEAD"] == 0.0
        assert s.by_bucket()["ai_growth"] == 10 * 100 * FX

    def test_it_is_listed_in_the_table_with_a_zero_value(self):
        assert "| DEAD |" in render_snapshot(self._zero())


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

    def test_two_rows_in_one_account_are_not_counted_as_two_accounts(self):
        # A split purchase inside 特定 is one holding, not a cross-account one.
        s = _snapshot(
            [
                Position(ticker="MSFT", shares=5, account="特定"),
                Position(ticker="MSFT", shares=5, account="特定"),
            ],
            quotes={"MSFT": _quote("MSFT", 100)},
        )
        assert s.account_count("MSFT") == 1
        assert "## 口座をまたぐ銘柄の合計" not in render_snapshot(s)

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
        assert "マイクロソフト" in text

    def test_non_positive_fx_reports_instead_of_dividing_by_zero(self):
        # --fx is rejected upstream, but a Snapshot can be built directly.
        s = Snapshot(
            holdings=Holdings(as_of="2026-08-09", positions=[], cash_jpy=1000),
            valued=[],
            fx=0.0,
        )
        text = render_snapshot(s)
        assert "円高シナリオを計算できません" in text
        assert "総資産インパクト" not in text

    def test_scenario_rates_come_from_config_when_present(self):
        s = _snapshot(
            [Position(ticker="MSFT", shares=10)], quotes={"MSFT": _quote("MSFT", 500)}
        )
        with patch("src.portfolio_snapshot.render.get_fx_scenario_rates", return_value=[120]):
            text = render_snapshot(s)
        assert "USD/JPY **120**" in text
        assert "USD/JPY **150**" not in text

    def test_scenario_rates_fall_back_when_config_is_absent(self):
        s = _snapshot(
            [Position(ticker="MSFT", shares=10)], quotes={"MSFT": _quote("MSFT", 500)}
        )
        with patch("src.portfolio_snapshot.render.get_fx_scenario_rates", return_value=[]):
            text = render_snapshot(s)
        for rate in FX_SCENARIOS:
            assert f"USD/JPY **{rate}**" in text

    @pytest.mark.parametrize("configured", [[0, -140, 130], [0], [-1]])
    def test_unusable_configured_rates_are_dropped(self, configured):
        # A hand-edited briefing.json can hold a zero or negative rate; those
        # would render a nonsense scenario, so they never reach the output.
        s = _snapshot(
            [Position(ticker="MSFT", shares=10)], quotes={"MSFT": _quote("MSFT", 500)}
        )
        with patch(
            "src.portfolio_snapshot.render.get_fx_scenario_rates", return_value=configured
        ):
            text = render_snapshot(s)
        assert "USD/JPY **0**" not in text
        assert "USD/JPY **-140**" not in text
        expected = [r for r in configured if r > 0] or list(FX_SCENARIOS)
        for rate in expected:
            assert f"USD/JPY **{rate:g}**" in text

    def test_every_configured_fx_scenario_is_priced(self):
        # Driven off FX_SCENARIOS so adding a rate can't silently go unrendered.
        s = _snapshot(
            [Position(ticker="MSFT", shares=10)], quotes={"MSFT": _quote("MSFT", 500)}
        )
        text = render_snapshot(s)
        for rate in FX_SCENARIOS:
            assert re.search(
                rf"USD/JPY \*\*{rate}\*\* まで円高が進んだ場合の総資産インパクト: \*\*-?\d+\.\d%\*\*",
                text,
            ), f"scenario {rate} is missing or its impact line changed shape"

    def test_unknown_totals_render_as_a_dash_without_a_stray_currency_symbol(self):
        assert "¥—" not in render_snapshot(_snapshot([]))

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


class TestCli:
    def _holdings_file(self, tmp_path):
        path = tmp_path / "holdings.json"
        path.write_text(
            json.dumps(
                {
                    "as_of": "2026-08-09",
                    "positions": [{"ticker": "MSFT", "shares": 10}],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_fx_option_values_at_the_given_rate_without_fetching_it(self, tmp_path, capsys):
        # Also the escape hatch for FX_FALLBACK: a stale fallback never has to
        # be edited in code to value the portfolio at a chosen rate.
        with patch(
            "src.portfolio_snapshot.valuation.fetch_stock_quotes",
            return_value={"MSFT": _quote("MSFT", 100)},
        ) as fetch:
            main(["--stdout", "--holdings", str(self._holdings_file(tmp_path)), "--fx", "200"])
        out = capsys.readouterr().out
        assert "USD/JPY **200.00**（指定値）" in out
        assert all(call.args[0] != ["JPY=X"] for call in fetch.call_args_list)

    def test_a_holdings_error_exits_with_the_message_not_a_traceback(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            main(["--stdout", "--holdings", str(tmp_path / "absent.json")])
        assert "holdings file not found" in str(excinfo.value)

    @pytest.mark.parametrize("bad", ["0", "-150"])
    def test_non_positive_fx_is_rejected_before_any_fetch(self, tmp_path, bad):
        with patch("src.portfolio_snapshot.valuation.fetch_stock_quotes") as fetch:
            with pytest.raises(SystemExit) as excinfo:
                main(["--stdout", "--holdings", str(self._holdings_file(tmp_path)), "--fx", bad])
        assert excinfo.value.code == 2  # argparse usage error
        fetch.assert_not_called()

    def test_without_fx_option_the_rate_is_fetched(self, tmp_path, capsys):
        def _quotes(tickers):
            if tickers == ["JPY=X"]:
                return {"JPY=X": _quote("JPY=X", 157.74, currency="JPY")}
            return {"MSFT": _quote("MSFT", 100)}

        with patch("src.portfolio_snapshot.valuation.fetch_stock_quotes", side_effect=_quotes):
            main(["--stdout", "--holdings", str(self._holdings_file(tmp_path))])
        assert "USD/JPY **157.74**（yfinance 直近値）" in capsys.readouterr().out


class TestBuildSnapshot:
    def test_fetches_fx_and_quotes_once(self):
        holdings = Holdings(as_of="2026-08-09", positions=[Position(ticker="MSFT", shares=2)])
        with patch(
            "src.portfolio_snapshot.valuation.fetch_stock_quotes",
            return_value={"MSFT": _quote("MSFT", 500)},
        ):
            s = build_snapshot(holdings, fx=FX)
        assert s.equity_jpy == 2 * 500 * FX
