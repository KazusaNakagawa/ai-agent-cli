from unittest.mock import MagicMock, patch

import pytest

from src.fetcher.stocks import (
    fetch_stock_move_map,
    fetch_stock_moves,
    fetch_stock_quotes,
    to_jpy_change_pct,
    to_yahoo_symbol,
)


class TestToYahooSymbol:
    """A bare TSE code has to reach Yahoo as ``NNNN.T``.

    Observed 2026-07-31: a portfolio entry of "4676" made yfinance answer
    ``Quote not found for symbol: 4676`` and the holdings table carried a fetch
    error for that line, silently, every day.
    """

    def test_all_digit_code_gains_the_tokyo_suffix(self):
        assert to_yahoo_symbol("4676") == "4676.T"

    def test_already_suffixed_code_is_untouched(self):
        assert to_yahoo_symbol("4676.T") == "4676.T"

    def test_us_ticker_is_untouched(self):
        assert to_yahoo_symbol("PLTR") == "PLTR"

    def test_surrounding_whitespace_is_trimmed(self):
        assert to_yahoo_symbol(" 4676 ") == "4676.T"


class TestFetchStockMoves:
    def _make_fast_info(self, last_price, previous_close):
        info = MagicMock()
        info.last_price = last_price
        info.previous_close = previous_close
        return info

    def test_positive_move(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._make_fast_info(110, 100)
            result = fetch_stock_moves(["PLTR"])
        assert "PLTR" in result
        assert "↑" in result
        assert "10.0%" in result

    def test_negative_move(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._make_fast_info(90, 100)
            result = fetch_stock_moves(["NVDA"])
        assert "↓" in result
        assert "10.0%" in result

    def test_multiple_tickers(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._make_fast_info(100, 100)
            result = fetch_stock_moves(["PLTR", "NVDA"])
        assert "PLTR" in result
        assert "NVDA" in result

    def test_error_returns_error_line(self):
        with patch("src.fetcher.stocks.yf.Ticker", side_effect=Exception("API down")):
            result = fetch_stock_moves(["PLTR"])
        assert "PLTR" in result
        assert "Stock fetch error" in result

    def test_empty_tickers_returns_empty_string(self):
        result = fetch_stock_moves([])
        assert result == ""


class TestFetchStockMoveMap:
    def _make_fast_info(self, last_price, previous_close):
        info = MagicMock()
        info.last_price = last_price
        info.previous_close = previous_close
        return info

    def test_returns_per_ticker_move_strings(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._make_fast_info(110, 100)
            moves = fetch_stock_move_map(["PLTR", "NVDA"])
        assert moves["PLTR"] == "↑10.0%  ($110.00)"
        assert moves["NVDA"] == "↑10.0%  ($110.00)"

    def test_error_ticker_gets_error_string(self):
        with patch("src.fetcher.stocks.yf.Ticker", side_effect=Exception("API down")):
            moves = fetch_stock_move_map(["PLTR"])
        assert "Stock fetch error" in moves["PLTR"]

    def test_empty_tickers_returns_empty_dict(self):
        assert fetch_stock_move_map([]) == {}


class TestToJpyChangePct:
    def test_moves_compound_rather_than_add(self):
        # -5.6% in USD on a day the yen weakened 0.8% is ~-4.84% in JPY,
        # not the -4.8% a naive addition would give.
        assert to_jpy_change_pct(-5.6, 0.8) == pytest.approx(-4.8448, abs=1e-4)

    def test_flat_fx_leaves_the_usd_move_unchanged(self):
        assert to_jpy_change_pct(-5.6, 0.0) == pytest.approx(-5.6)

    def test_yen_strengthening_deepens_a_loss(self):
        assert to_jpy_change_pct(-5.6, -1.0) < -5.6


class TestCurrencyDetection:
    def _fast_info(self, currency=None):
        info = MagicMock()
        info.last_price = 110
        info.previous_close = 100
        if currency is None:
            # Simulate a fast_info that does not expose `currency` at all.
            del info.currency
        else:
            info.currency = currency
        return info

    def test_currency_from_fast_info_is_used(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info("jpy")
            quotes = fetch_stock_quotes(["4676.T"])
        assert quotes["4676.T"].currency == "JPY"

    def test_dot_t_suffix_falls_back_to_jpy(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info()
            quotes = fetch_stock_quotes(["4676.T"])
        assert quotes["4676.T"].currency == "JPY"

    def test_all_digit_ticker_falls_back_to_jpy(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info()
            quotes = fetch_stock_quotes(["4676"])
        assert quotes["4676"].currency == "JPY"

    def test_bare_tse_code_is_requested_with_the_suffix(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info()
            quotes = fetch_stock_quotes(["4676"])
        MockTicker.assert_called_once_with("4676.T")
        # Keyed by the configured form so the holdings table keeps its label.
        assert "4676" in quotes
        assert quotes["4676"].ticker == "4676"

    def test_plain_ticker_falls_back_to_usd(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info()
            quotes = fetch_stock_quotes(["PLTR"])
        assert quotes["PLTR"].currency == "USD"

    def test_mocked_non_string_currency_does_not_crash(self):
        # A bare MagicMock returns a MagicMock for `.currency`; it must fall
        # back rather than be treated as a currency code.
        info = MagicMock()
        info.last_price = 110
        info.previous_close = 100
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = info
            quotes = fetch_stock_quotes(["PLTR"])
        assert quotes["PLTR"].currency == "USD"


class TestFetchStockMovesWithFx:
    def _fast_info(self, last_price, previous_close, currency="USD"):
        info = MagicMock()
        info.last_price = last_price
        info.previous_close = previous_close
        info.currency = currency
        return info

    def test_usd_ticker_reports_both_currencies(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(94.4, 100.0)
            result = fetch_stock_moves(["PLTR"], fx_change_pct=0.8)
        assert "ドル建て ↓5.6%" in result
        assert "円建て ↓4.8%" in result

    def test_jpy_ticker_is_not_double_converted(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(110, 100, currency="JPY")
            result = fetch_stock_moves(["4676.T"], fx_change_pct=0.8)
        assert "円建て" not in result
        assert "↑10.0%" in result

    def test_jpy_price_is_not_labelled_with_a_dollar_sign(self):
        """Regression guard: a JPY listing used to render as ``$4206.00``."""
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(4206, 4156, currency="JPY")
            result = fetch_stock_moves(["4676.T"], fx_change_pct=0.8)
        assert "¥4206.00" in result
        assert "$" not in result

    def test_usd_price_keeps_the_dollar_sign(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(110, 100)
            result = fetch_stock_moves(["PLTR"], fx_change_pct=0.8)
        assert "$110.00" in result

    def test_unknown_currency_falls_back_to_its_iso_code(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(110, 100, currency="CHF")
            result = fetch_stock_moves(["NESN.SW"])
        assert "CHF 110.00" in result

    def test_omitting_fx_keeps_the_previous_output(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(110, 100)
            result = fetch_stock_moves(["PLTR"])
        assert result == "PLTR: ↑10.0%  ($110.00)"

    def test_fetch_error_survives_the_fx_path(self):
        with patch("src.fetcher.stocks.yf.Ticker", side_effect=Exception("API down")):
            result = fetch_stock_moves(["PLTR"], fx_change_pct=0.8)
        assert "Stock fetch error" in result
