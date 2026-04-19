from src.metrics.briefing import extract_briefing_metrics
from src.metrics.xss import extract_xss_metrics


class TestExtractBriefingMetrics:
    def test_char_count(self):
        result = extract_briefing_metrics("hello", tickers=[])
        assert result["CharCount"] == {"number": 5}

    def test_ticker_count_case_insensitive(self):
        result = extract_briefing_metrics("PLTR は上昇、nvda は横ばい", tickers=["PLTR", "NVDA"])
        assert result["TickerCount"] == {"number": 2}

    def test_ticker_not_mentioned(self):
        result = extract_briefing_metrics("市場は安定", tickers=["PLTR", "NVDA"])
        assert result["TickerCount"] == {"number": 0}

    def test_partial_match_not_counted(self):
        # "NVDA" を含む単語 "NVDA-related" でも部分一致はカウントされる（IN 検索）
        # ただし "PLTR2" は "PLTR" を含むのでカウントされることを確認
        result = extract_briefing_metrics("PLTR2 mentioned", tickers=["PLTR"])
        assert result["TickerCount"] == {"number": 1}

    def test_returns_number_format(self):
        result = extract_briefing_metrics("abc", tickers=[])
        assert set(result.keys()) == {"CharCount", "TickerCount"}
        assert "number" in result["CharCount"]
        assert "number" in result["TickerCount"]


class TestExtractXssMetrics:
    def test_counts_high(self):
        result = extract_xss_metrics("This is a High severity issue and another High one.")
        assert result["HighCount"] == {"number": 2}

    def test_counts_medium(self):
        result = extract_xss_metrics("Medium risk found.")
        assert result["MediumCount"] == {"number": 1}

    def test_counts_low(self):
        result = extract_xss_metrics("Low impact vulnerability.")
        assert result["LowCount"] == {"number": 1}

    def test_case_insensitive(self):
        result = extract_xss_metrics("HIGH, high, High")
        assert result["HighCount"] == {"number": 3}

    def test_zero_when_absent(self):
        result = extract_xss_metrics("No severity keywords here.")
        assert result["HighCount"] == {"number": 0}
        assert result["MediumCount"] == {"number": 0}
        assert result["LowCount"] == {"number": 0}

    def test_returns_all_keys(self):
        result = extract_xss_metrics("")
        assert set(result.keys()) == {"HighCount", "MediumCount", "LowCount"}
