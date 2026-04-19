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
        # "PLTR2" は単語境界でマッチしないため PLTR としてカウントされない
        result = extract_briefing_metrics("PLTR2 mentioned", tickers=["PLTR"])
        assert result["TickerCount"] == {"number": 0}

    def test_exact_match_counted(self):
        result = extract_briefing_metrics("PLTR mentioned", tickers=["PLTR"])
        assert result["TickerCount"] == {"number": 1}

    def test_returns_number_format(self):
        result = extract_briefing_metrics("abc", tickers=[])
        assert set(result.keys()) == {"CharCount", "TickerCount"}
        assert "number" in result["CharCount"]
        assert "number" in result["TickerCount"]


class TestExtractXssMetrics:
    def test_counts_structured_high(self):
        result = extract_xss_metrics("深刻度: High\n深刻度: High")
        assert result["HighCount"] == {"number": 2}

    def test_counts_structured_medium(self):
        result = extract_xss_metrics("深刻度: Medium")
        assert result["MediumCount"] == {"number": 1}

    def test_counts_structured_low(self):
        result = extract_xss_metrics("深刻度: Low")
        assert result["LowCount"] == {"number": 1}

    def test_prose_high_not_counted(self):
        # 散文中の "high" は深刻度ラベルではないのでカウントしない
        result = extract_xss_metrics("This is a high risk issue with high-profile impact.")
        assert result["HighCount"] == {"number": 0}

    def test_prose_low_not_counted(self):
        result = extract_xss_metrics("Low likelihood of exploitation.")
        assert result["LowCount"] == {"number": 0}

    def test_case_insensitive_label(self):
        result = extract_xss_metrics("深刻度: HIGH\n深刻度: high")
        assert result["HighCount"] == {"number": 2}

    def test_fullwidth_colon(self):
        # プロンプト出力が全角コロンになるケース
        result = extract_xss_metrics("深刻度：High")
        assert result["HighCount"] == {"number": 1}

    def test_zero_when_absent(self):
        result = extract_xss_metrics("No severity labels here.")
        assert result["HighCount"] == {"number": 0}
        assert result["MediumCount"] == {"number": 0}
        assert result["LowCount"] == {"number": 0}

    def test_returns_all_keys(self):
        result = extract_xss_metrics("")
        assert set(result.keys()) == {"HighCount", "MediumCount", "LowCount"}
