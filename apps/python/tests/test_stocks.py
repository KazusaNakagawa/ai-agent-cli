from unittest.mock import MagicMock, patch

from src.fetcher.stocks import fetch_stock_move_map, fetch_stock_moves


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
        assert "取得エラー" in result

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
        assert "取得エラー" in moves["PLTR"]

    def test_empty_tickers_returns_empty_dict(self):
        assert fetch_stock_move_map([]) == {}
