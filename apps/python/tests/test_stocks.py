from unittest.mock import MagicMock, patch

import pytest

from src.fetcher.stocks import (
    fetch_stock_move_map,
    fetch_stock_moves,
    fetch_stock_quotes,
    to_jpy_change_pct,
)


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

    def test_omitting_fx_keeps_the_previous_output(self):
        with patch("src.fetcher.stocks.yf.Ticker") as MockTicker:
            MockTicker.return_value.fast_info = self._fast_info(110, 100)
            result = fetch_stock_moves(["PLTR"])
        assert result == "PLTR: ↑10.0%  ($110.00)"

    def test_fetch_error_survives_the_fx_path(self):
        with patch("src.fetcher.stocks.yf.Ticker", side_effect=Exception("API down")):
            result = fetch_stock_moves(["PLTR"], fx_change_pct=0.8)
        assert "Stock fetch error" in result
