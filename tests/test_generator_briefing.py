from unittest.mock import patch

import pytest

from src.config import BriefingConfig, Conflict, GeopoliticalConfig, PortfolioConfig, WatchSector
from src.generator.briefing import (
    _build_geopolitical_context,
    _build_watch_sectors_context,
    generate_briefing,
)


def _make_config(**overrides):
    defaults = dict(
        portfolio=PortfolioConfig(tickers=["PLTR", "NVDA"], themes=["AI", "Defense"]),
        geopolitical=GeopoliticalConfig(conflicts=[]),
        watch_sectors=[WatchSector(sector="Tech", tickers=["AAPL"])],
    )
    defaults.update(overrides)
    return BriefingConfig(**defaults)


class TestBuildGeopoliticalContext:
    def test_empty_conflicts_returns_empty_string(self):
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=[]))
        assert _build_geopolitical_context(config) == ""

    def test_includes_name_sectors_tickers_notes(self):
        conflict = Conflict(
            name="中東情勢",
            affected_sectors=["エネルギー", "防衛"],
            related_tickers=["XOM", "RTX"],
            notes="原油供給に影響",
        )
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=[conflict]))
        result = _build_geopolitical_context(config)
        assert "中東情勢" in result
        assert "エネルギー、防衛" in result
        assert "XOM、RTX" in result
        assert "原油供給に影響" in result

    def test_optional_fields_omitted_when_empty(self):
        conflict = Conflict(name="紛争A", affected_sectors=["金融"])
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=[conflict]))
        result = _build_geopolitical_context(config)
        assert "関連銘柄" not in result
        assert "背景" not in result

    def test_multiple_conflicts_separated_by_blank_line(self):
        conflicts = [
            Conflict(name="紛争A", affected_sectors=["金融"]),
            Conflict(name="紛争B", affected_sectors=["エネルギー"]),
        ]
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=conflicts))
        result = _build_geopolitical_context(config)
        assert "紛争A" in result
        assert "紛争B" in result


class TestBuildWatchSectorsContext:
    def test_includes_sector_and_tickers(self):
        sectors = [WatchSector(sector="AI半導体", tickers=["NVDA", "AMD"])]
        config = _make_config(watch_sectors=sectors)
        result = _build_watch_sectors_context(config)
        assert "AI半導体" in result
        assert "NVDA、AMD" in result

    def test_notes_included_when_present(self):
        sectors = [WatchSector(sector="EV", tickers=["TSLA"], notes="充電インフラ動向注視")]
        config = _make_config(watch_sectors=sectors)
        result = _build_watch_sectors_context(config)
        assert "充電インフラ動向注視" in result

    def test_notes_omitted_when_absent(self):
        sectors = [WatchSector(sector="EV", tickers=["TSLA"])]
        config = _make_config(watch_sectors=sectors)
        result = _build_watch_sectors_context(config)
        assert "注目点" not in result


class TestGenerateBriefing:
    def _mock_run(self, responses: dict):
        def side_effect(prompt, label, timeout):
            return responses[label]
        return side_effect

    def test_success_combines_main_and_sectors(self):
        config = _make_config()
        mock = self._mock_run({"メイン分析": "メイン結果", "セクタースイープ": "セクター結果"})
        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_briefing("PLTR: +2%", config)
        assert "メイン結果" in result
        assert "セクター動向" in result
        assert "セクター結果" in result

    def test_main_failure_raises(self):
        config = _make_config()

        def mock(prompt, label, timeout):
            if label == "メイン分析":
                raise RuntimeError("API error")
            return "sectors ok"

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            with pytest.raises(RuntimeError, match="メイン分析"):
                generate_briefing("PLTR: +2%", config)

    def test_sectors_failure_returns_degraded_output(self):
        config = _make_config()

        def mock(prompt, label, timeout):
            if label == "セクタースイープ":
                raise RuntimeError("sectors error")
            return "main ok"

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_briefing("PLTR: +2%", config)

        assert "main ok" in result
        assert "セクター動向の取得に失敗しました" in result
