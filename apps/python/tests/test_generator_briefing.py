from unittest.mock import patch

import pytest

from src.config import BriefingConfig, Conflict, GeopoliticalConfig, PortfolioConfig, WatchEvent, WatchSector
from src.constants import RETRY_MAX_ATTEMPTS_BRIEFING
from src.generator.briefing import (
    build_geopolitical_context,
    build_watch_events_context,
    build_watch_sectors_context,
    generate_briefing,
    load_briefing_few_shot,
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
        assert build_geopolitical_context(config) == ""

    def test_includes_name_sectors_tickers_notes(self):
        conflict = Conflict(
            name="中東情勢",
            affected_sectors=["エネルギー", "防衛"],
            related_tickers=["XOM", "RTX"],
            notes="原油供給に影響",
        )
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=[conflict]))
        result = build_geopolitical_context(config)
        assert "中東情勢" in result
        assert "エネルギー、防衛" in result
        assert "XOM、RTX" in result
        assert "原油供給に影響" in result

    def test_optional_fields_omitted_when_empty(self):
        conflict = Conflict(name="紛争A", affected_sectors=["金融"])
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=[conflict]))
        result = build_geopolitical_context(config)
        assert "関連銘柄" not in result
        assert "背景" not in result

    def test_multiple_conflicts_separated_by_blank_line(self):
        conflicts = [
            Conflict(name="紛争A", affected_sectors=["金融"]),
            Conflict(name="紛争B", affected_sectors=["エネルギー"]),
        ]
        config = _make_config(geopolitical=GeopoliticalConfig(conflicts=conflicts))
        result = build_geopolitical_context(config)
        assert "紛争A" in result
        assert "紛争B" in result


class TestBuildWatchSectorsContext:
    def test_includes_sector_and_tickers(self):
        sectors = [WatchSector(sector="AI半導体", tickers=["NVDA", "AMD"])]
        config = _make_config(watch_sectors=sectors)
        result = build_watch_sectors_context(config)
        assert "AI半導体" in result
        assert "NVDA、AMD" in result

    def test_notes_included_when_present(self):
        sectors = [WatchSector(sector="EV", tickers=["TSLA"], notes="充電インフラ動向注視")]
        config = _make_config(watch_sectors=sectors)
        result = build_watch_sectors_context(config)
        assert "充電インフラ動向注視" in result

    def test_notes_omitted_when_absent(self):
        sectors = [WatchSector(sector="EV", tickers=["TSLA"])]
        config = _make_config(watch_sectors=sectors)
        result = build_watch_sectors_context(config)
        assert "注目点" not in result


class TestBuildWatchEventsContext:
    def test_empty_events_returns_empty_string(self):
        config = _make_config(watch_events=[])
        assert build_watch_events_context(config) == ""

    def test_includes_name_trigger_sectors_tickers_notes(self):
        event = WatchEvent(
            name="SpaceX IPO",
            trigger="SECへのS-1提出",
            affected_sectors=["宇宙", "テクノロジー"],
            related_tickers=["RKLB", "ASTS"],
            notes="宇宙セクター再評価トリガー",
        )
        config = _make_config(watch_events=[event])
        result = build_watch_events_context(config)
        assert "SpaceX IPO" in result
        assert "SECへのS-1提出" in result
        assert "宇宙、テクノロジー" in result
        assert "RKLB、ASTS" in result
        assert "宇宙セクター再評価トリガー" in result

    def test_optional_fields_omitted_when_empty(self):
        event = WatchEvent(name="IPO", trigger="上場申請", affected_sectors=["テクノロジー"])
        config = _make_config(watch_events=[event])
        result = build_watch_events_context(config)
        assert "関連銘柄" not in result
        assert "背景" not in result

    def test_affected_sectors_omitted_when_empty(self):
        event = WatchEvent(name="IPO", trigger="上場申請", affected_sectors=[])
        config = _make_config(watch_events=[event])
        result = build_watch_events_context(config)
        assert "影響セクター" not in result


class TestGenerateBriefing:
    def _mock_run(self, responses: dict):
        def side_effect(prompt, label, timeout, **kwargs):
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

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                raise RuntimeError("API error")
            return "sectors ok"

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            with pytest.raises(RuntimeError, match="main analysis"):
                generate_briefing("PLTR: +2%", config)

    def test_sectors_failure_returns_degraded_output(self):
        config = _make_config()

        def mock(prompt, label, timeout, **kwargs):
            if label == "セクタースイープ":
                raise RuntimeError("sectors error")
            return "main ok"

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_briefing("PLTR: +2%", config)

        assert "main ok" in result
        assert "セクター動向の取得に失敗しました" in result

    def test_main_prompt_includes_few_shot_asset(self):
        """メイン分析プロンプトに few-shot 例（#192 のアセット）が注入される。"""
        config = _make_config()
        captured = {}

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                captured["prompt"] = prompt
            return "ok"

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            generate_briefing("PLTR: +2%", config)

        few_shot = load_briefing_few_shot()
        # 例の先頭の特徴的な見出しがそのままプロンプトに含まれる
        assert "### 今日のサマリー（1文）" in captured["prompt"]
        assert few_shot.strip() in captured["prompt"]

    def test_main_and_sectors_use_bounded_briefing_retry_budget(self):
        """Verifies: both run_claude calls pass max_attempts=RETRY_MAX_ATTEMPTS_BRIEFING.
        Why: the module default (RETRY_MAX_ATTEMPTS=3) triples the per-run
        token cost on a string of transient errors (#406); briefing calls opt
        into a tighter, explicit budget instead of relying on the default.
        """
        config = _make_config()
        captured = {}

        def mock(prompt, label, timeout, **kwargs):
            captured[label] = kwargs.get("max_attempts")
            return "ok"

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            generate_briefing("PLTR: +2%", config)

        assert captured["メイン分析"] == RETRY_MAX_ATTEMPTS_BRIEFING
        assert captured["セクタースイープ"] == RETRY_MAX_ATTEMPTS_BRIEFING


class TestLoadBriefingFewShot:
    def test_asset_is_non_empty_and_follows_format(self):
        text = load_briefing_few_shot()
        assert text.strip()
        # 出力フォーマットの主要セクションを型として含む
        for heading in ("### 今日のサマリー", "### なぜ動いたか", "### 自分への示唆", "### 参考記事"):
            assert heading in text
