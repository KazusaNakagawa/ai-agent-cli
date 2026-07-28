from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.config import FxConfig, FxPair
from src.fetcher.fx import (
    FxQuote,
    fetch_fx_context,
    fetch_fx_quote,
    format_fx_context,
    format_fx_quote,
)


def _history(closes):
    """Build a yfinance-shaped history frame from a list of closes."""
    return pd.DataFrame({"Close": closes})


def _patch_history(closes):
    ticker = MagicMock()
    ticker.history.return_value = _history(closes)
    return patch("src.fetcher.fx.yf.Ticker", return_value=ticker)


class TestFetchFxQuote:
    def test_reports_rate_and_day_change(self):
        with _patch_history([100.0, 110.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY")
        assert quote.rate == 110.0
        assert quote.change_pct == pytest.approx(10.0)

    def test_range_position_at_high_is_100(self):
        with _patch_history([100.0, 120.0, 150.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY")
        assert quote.range_low == 100.0
        assert quote.range_high == 150.0
        assert quote.range_position_pct == pytest.approx(100.0)

    def test_range_position_at_low_is_zero(self):
        with _patch_history([150.0, 120.0, 100.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY")
        assert quote.range_position_pct == pytest.approx(0.0)

    def test_flat_year_reports_mid_range_instead_of_dividing_by_zero(self):
        with _patch_history([150.0, 150.0, 150.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY")
        assert quote.range_position_pct == pytest.approx(50.0)

    def test_ma200_skipped_when_history_is_short(self):
        with _patch_history([100.0, 110.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY")
        assert quote.ma200 is None
        assert quote.ma200_dev_pct is None

    def test_ma200_computed_when_history_is_long_enough(self):
        # 199 closes at 100 plus a final 110 -> MA200 over the last 200 sessions.
        with _patch_history([100.0] * 199 + [110.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY")
        assert quote.ma200 == pytest.approx(100.05)
        assert quote.ma200_dev_pct == pytest.approx(9.945, abs=0.01)

    def test_band_is_carried_through(self):
        with _patch_history([100.0, 110.0]):
            quote = fetch_fx_quote("JPY=X", "USD/JPY", band_low=150, band_high=165)
        assert quote.band_low == 150
        assert quote.band_high == 165

    def test_fetch_failure_returns_none(self):
        with patch("src.fetcher.fx.yf.Ticker", side_effect=Exception("API down")):
            assert fetch_fx_quote("JPY=X", "USD/JPY") is None

    def test_empty_history_returns_none(self):
        with _patch_history([]):
            assert fetch_fx_quote("JPY=X", "USD/JPY") is None

    def test_single_close_returns_none(self):
        with _patch_history([150.0]):
            assert fetch_fx_quote("JPY=X", "USD/JPY") is None


class TestFormatting:
    def _quote(self, **overrides):
        base = dict(
            label="USD/JPY",
            rate=163.85,
            change_pct=0.8,
            range_low=140.0,
            range_high=165.0,
            range_position_pct=95.4,
            ma200=154.3,
            ma200_dev_pct=6.2,
        )
        base.update(overrides)
        return FxQuote(**base)

    def test_quote_line_leads_with_level_not_day_change(self):
        line = format_fx_quote(self._quote())
        assert line.index("163.85") < line.index("+0.80%")

    def test_quote_line_includes_range_and_ma(self):
        line = format_fx_quote(self._quote())
        assert "1年レンジ 140.00〜165.00" in line
        assert "レンジ内位置 95%" in line
        assert "200日線 154.30" in line

    def test_quote_line_omits_ma_when_absent(self):
        line = format_fx_quote(self._quote(ma200=None, ma200_dev_pct=None))
        assert "200日線" not in line

    def test_quote_line_includes_band_when_configured(self):
        line = format_fx_quote(self._quote(band_low=150, band_high=165))
        assert "参照バンド 150〜165" in line

    def test_context_without_scenarios_is_just_rate_lines(self):
        block = format_fx_context([self._quote()])
        assert "USD/JPY" in block
        assert "シナリオ" not in block

    def test_scenario_table_scales_impact_by_usd_share(self):
        block = format_fx_context(
            [self._quote()], usd_asset_share=0.85, scenario_rates=[150.0]
        )
        # (150/163.85 - 1) * 0.85 = -7.18%
        assert "ドル建て資産の比率: 85%" in block
        assert "150円: -7.18%" in block

    def test_scenarios_skipped_without_usd_share(self):
        block = format_fx_context([self._quote()], scenario_rates=[150.0])
        assert "シナリオ" not in block

    def test_zero_usd_share_is_honoured_not_treated_as_unset(self):
        """0.0 is a real answer ("no USD exposure"), not a missing value."""
        block = format_fx_context(
            [self._quote()], usd_asset_share=0.0, scenario_rates=[150.0]
        )
        assert "ドル建て資産の比率: 0%" in block
        assert "150円: +0.00%" in block

    def test_scenarios_use_usd_jpy_not_the_first_dollar_pair(self):
        """A second USD pair must not drive the scenario table.

        Regression guard: matching on "USD" alone picked EUR/USD when it was
        listed first, computing impact against ~1.08 instead of ~163.85 and
        reporting +11720% where -7.19% was correct.
        """
        eur_usd = self._quote(label="EUR/USD", rate=1.08)
        block = format_fx_context(
            [eur_usd, self._quote()], usd_asset_share=0.85, scenario_rates=[150.0]
        )
        assert "150円: -7.18%" in block

    def test_no_scenario_table_when_usd_jpy_is_absent(self):
        eur_usd = self._quote(label="EUR/USD", rate=1.08)
        block = format_fx_context(
            [eur_usd], usd_asset_share=0.85, scenario_rates=[150.0]
        )
        assert "シナリオ" not in block

    def test_empty_quotes_reports_no_data(self):
        assert format_fx_context([]) == "(取得なし)"


class TestFetchFxContext:
    def _config(self, **overrides):
        config = MagicMock()
        config.fx = FxConfig(
            pairs=[FxPair(symbol="JPY=X", label="USD/JPY")],
            **overrides,
        )
        return config

    def test_returns_block_and_usd_jpy_day_change(self):
        with _patch_history([100.0, 110.0]):
            block, change = fetch_fx_context(self._config())
        assert "USD/JPY" in block
        assert change == pytest.approx(10.0)

    def test_disabled_when_no_pairs_configured(self):
        config = MagicMock()
        config.fx = FxConfig()
        assert fetch_fx_context(config) == ("", None)

    def test_missing_fx_attribute_is_treated_as_disabled(self):
        config = MagicMock(spec=[])
        assert fetch_fx_context(config) == ("", None)

    def test_total_fetch_failure_degrades_to_no_fx(self):
        with patch("src.fetcher.fx.yf.Ticker", side_effect=Exception("API down")):
            assert fetch_fx_context(self._config()) == ("", None)

    def test_non_jpy_pair_yields_no_conversion_rate(self):
        config = MagicMock()
        config.fx = FxConfig(pairs=[FxPair(symbol="EURUSD=X", label="EUR/USD")])
        with _patch_history([1.0, 1.1]):
            block, change = fetch_fx_context(config)
        assert "EUR/USD" in block
        assert change is None
