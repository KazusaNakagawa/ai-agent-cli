import json
from unittest.mock import patch

import pytest

from tests.conftest import HIJACKED_SKILL_COMPLETION_REPORT
from src.config import BriefingConfig, Conflict, GeopoliticalConfig, PortfolioConfig, WatchEvent, WatchSector
from src.constants import RETRY_MAX_ATTEMPTS_BRIEFING, TIMEOUT_BRIEFING_SECTORS
from src.generator.briefing import (
    SECTORS_FAILED_NOTICE,
    build_geopolitical_context,
    build_watch_events_context,
    build_watch_sectors_context,
    generate_briefing,
    generate_sectors,
    is_degraded_briefing,
    load_briefing_few_shot,
    looks_like_briefing,
    merge_recovered_sectors,
)
from src.generator.briefscript_render import splice_holdings


def _sectors_json(text: str = "セクター結果。", sector: str = "Tech") -> str:
    """A valid sector-sweep payload whose one claim renders as ``text`` (#514)."""
    return json.dumps({
        "sectors": [{"sector": sector, "claims": [{"text": text, "confidence": "inferred"}]}],
    }, ensure_ascii=False)


_SECTORS_OK = _sectors_json()


def _main_json(**overrides) -> str:
    """A valid main-analysis payload (#515); ``overrides`` replace top-level fields."""
    data = {
        "summary": "今日のまとめ。",
        "stories": [{"title": "話題A", "claims": [
            {"text": "記事で確認した事実。", "confidence": "confirmed", "source_ids": ["s1"]},
        ]}],
        "references": [{"category": "カテゴリA", "source_ids": ["s1"]}],
        "sources": [{"id": "s1", "title": "記事1", "url": "https://example.com/s1"}],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


_MAIN_OK = _main_json()
# Long enough that a sectors-only body clears looks_like_briefing.
_SECTORS_LONG = _sectors_json("セクター本文。" * 40)


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
        mock = self._mock_run({"メイン分析": "メイン結果", "セクタースイープ": _SECTORS_OK})
        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_briefing("PLTR: +2%", config)
        assert "メイン結果" in result
        assert "セクター動向" in result
        assert "セクター結果" in result

    def test_main_failure_keeps_successful_sector_sweep(self):
        """Verifies: a main-analysis failure degrades to a sectors-only briefing.
        Why: main and sectors run independently, and a WebSearch 529 storm can
        blow the main analysis' wall clock while the sector sweep finishes fine
        (observed 2026-07-26: a 10,721-char sweep was discarded). Raising here
        threw away work that was already paid for.
        """
        config = _make_config()

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                raise RuntimeError("claude CLI timed out (メイン分析)")
            return _SECTORS_LONG

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_briefing("PLTR: +2%", config)

        assert "セクター本文。" in result
        assert "メイン分析の取得に失敗しました" in result
        assert "claude CLI timed out" in result

    def test_main_failure_output_still_looks_like_a_briefing(self):
        """Regression guard: the degraded body must clear looks_like_briefing().
        A long claude CLI error detail (run_claude truncates at 2000 chars) must
        not push the first "### " heading past _HEADING_SEARCH_WINDOW, or
        handler.py would reject the body and discard the sweep anyway.
        """
        config = _make_config()

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                raise RuntimeError("x" * 2000)
            return _SECTORS_LONG

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_briefing("PLTR: +2%", config)

        assert looks_like_briefing(result) is True

    def test_degraded_bodies_are_detectable(self):
        """Both half-failed shapes must be recognizable as degraded, so the
        handler's skip guard can let a retry through (see test_handlers)."""
        config = _make_config()
        long_body = "### 今日の見出し\n\n" + "本文。" * 40

        def main_fails(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                raise RuntimeError("boom")
            return _SECTORS_LONG

        def sectors_fail(prompt, label, timeout, **kwargs):
            if label == "セクタースイープ":
                raise RuntimeError("boom")
            return long_body

        for mock in (main_fails, sectors_fail):
            with patch("src.generator.briefing.run_claude", side_effect=mock):
                assert is_degraded_briefing(generate_briefing("PLTR: +2%", config)) is True

        with patch("src.generator.briefing.run_claude", side_effect=self._mock_run(
            {"メイン分析": long_body, "セクタースイープ": _SECTORS_LONG}
        )):
            assert is_degraded_briefing(generate_briefing("PLTR: +2%", config)) is False

    def test_both_failures_raise(self):
        """Nothing was produced, so there is no briefing to deliver."""
        config = _make_config()

        def mock(prompt, label, timeout, **kwargs):
            raise RuntimeError("API error")

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


class TestLooksLikeBriefing:
    def test_real_briefing_shape_passes(self):
        """成功系: 見出し付きの長文はブリーフィングとして認識される。"""
        text = "### 今日のサマリー（1文）\n\n" + "本文です。" * 40
        assert looks_like_briefing(text) is True

    def test_skill_completion_report_fails(self):
        """失敗系: notion-import スキルがハイジャックして返す短い完了報告
        （#409 で実際に観測された文面）はブリーフィングとして扱わない。"""
        assert looks_like_briefing(HIJACKED_SKILL_COMPLETION_REPORT) is False

    def test_long_text_without_heading_fails(self):
        """境界値: 見出しが無ければ、どれだけ長くても不合格。"""
        text = "見出しの無い長文です。" * 40
        assert looks_like_briefing(text) is False

    def test_short_text_with_heading_fails(self):
        """境界値: 見出しがあっても最低文字数に満たなければ不合格。"""
        text = "### 今日のサマリー"
        assert looks_like_briefing(text) is False

    def test_short_preamble_before_heading_passes(self):
        """成功系: 実運用で頻出する前置き文（本番で実際に観測、#410 での回帰）。
        claude CLI はしばしば "情報が揃いました。ブリーフィングをまとめます。" のような
        一文の後に本題の見出しを続けて返す。これを誤って弾いてはならない。"""
        text = "情報が揃いました。ブリーフィングをまとめます。\n\n---\n\n### 今日のサマリー（1文）\n\n" + "本文です。" * 40
        assert looks_like_briefing(text) is True

    def test_heading_far_into_unrelated_text_fails(self):
        """境界値: 見出しが遠く離れた位置にしか出現しない無関係な長文は不合格
        （レビュー指摘 #410 — ただし現実の短い前置きは許容する程度の余白を残す）。"""
        text = "見出しではない前置きが続きます。" * 100 + "\n\n### 途中に出てくる見出し\n\n" + "本文です。" * 20
        assert looks_like_briefing(text) is False


class TestLoadBriefingFewShot:
    def test_asset_is_non_empty_and_follows_format(self):
        text = load_briefing_few_shot()
        assert text.strip()
        # 出力フォーマットの主要セクションを型として含む
        for heading in ("### 今日のサマリー", "### なぜ動いたか", "### 自分への示唆", "### 参考記事"):
            assert heading in text


class TestMergeRecoveredSectors:
    def test_replaces_failure_notice_with_recovered_sectors(self):
        degraded = (
            "### 本日の相場\n本文\n\n---\n\n"
            f"{SECTORS_FAILED_NOTICE}\n"
            "claude CLI error [セクタースイープ] rc=1: {...}"
        )

        merged = merge_recovered_sectors(degraded, "### 半導体\n強い")

        assert SECTORS_FAILED_NOTICE not in merged
        assert merged.startswith("### 本日の相場\n本文")
        assert merged.endswith("## セクター動向\n\n### 半導体\n強い")

    def test_body_without_failure_notice_is_unchanged(self):
        body = "### 本日の相場\n本文\n\n---\n\n## セクター動向\n\n### 半導体\n強い"

        assert merge_recovered_sectors(body, "新しいセクター") == body


class TestGenerateSectors:
    def test_runs_only_the_sector_sweep_and_returns_its_text(self):
        config = _make_config()
        calls = []

        def mock(prompt, label, timeout, **kwargs):
            calls.append((label, timeout, kwargs.get("max_attempts")))
            return _sectors_json("強い")

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            result = generate_sectors("PLTR: +2%", config)

        assert result == "### 今日のセクター動向（全セクター）\n\n#### Tech\n- 〔推測〕強い"
        assert calls == [
            ("セクタースイープ", TIMEOUT_BRIEFING_SECTORS, RETRY_MAX_ATTEMPTS_BRIEFING)
        ]

    def test_prompt_carries_the_configured_watch_sectors(self):
        config = _make_config(watch_sectors=[WatchSector(sector="防衛", tickers=["RTX"])])
        prompts = []

        def mock(prompt, label, timeout, **kwargs):
            prompts.append(prompt)
            return _sectors_json(sector="防衛")

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            generate_sectors("PLTR: +2%", config)

        assert "防衛" in prompts[0]
        assert "RTX" in prompts[0]


class TestBriefScriptHoldings:
    """Holdings generated as BriefScript and spliced into the main body (#506)."""

    # The no-quotes path still asks the main analysis for Markdown.
    _MAIN_MD = (
        "### 今日のサマリー（1文）\n\nサマリー。\n\n---\n\n"
        "### 自分への示唆\n\n#### PLTR：旧見出し\n- 旧本文（Markdown フォールバック）\n\n---\n\n"
        "### 参考記事\n\n- [a](https://example.com)\n"
    )

    @classmethod
    def _main(cls, kwargs):
        return _MAIN_OK if "json_schema" in kwargs else cls._MAIN_MD

    def _config(self):
        return _make_config(portfolio=PortfolioConfig(tickers=["PLTR", "NVDA"], themes=["AI"]))

    @staticmethod
    def _quotes():
        from src.fetcher.stocks import StockQuote

        return {
            "PLTR": StockQuote("PLTR", 196.75, 197.14, -0.2),
            "NVDA": StockQuote("NVDA", 100.0, 99.0, 1.0),
        }

    @staticmethod
    def _payload(ticker="PLTR", source_ids=("s1",)):
        import json

        return json.dumps({
            "holdings": [{"ticker": ticker, "claims": [
                {"text": "決算が予想を上回った。", "confidence": "confirmed",
                 "source_ids": list(source_ids)},
            ]}],
            "sources": [{"id": "s1", "title": "t", "url": "https://example.com/s1"}],
        })

    def _run(self, holdings_responses, quotes="default", fx_change_pct=-0.9):
        calls = {"holdings": [], "kwargs": None}
        responses = iter(holdings_responses)

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                return self._main(kwargs)
            if label == "セクタースイープ":
                return _SECTORS_OK
            calls["holdings"].append(prompt)
            calls["kwargs"] = kwargs
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

        quotes = self._quotes() if quotes == "default" else quotes
        with patch("src.generator.briefing.run_claude", side_effect=mock):
            out = generate_briefing("PLTR: ↓0.2%", self._config(), "fx",
                                    quotes=quotes, fx_change_pct=fx_change_pct)
        return out, calls

    def test_valid_briefscript_replaces_markdown_holdings(self):
        out, calls = self._run([self._payload()])
        assert "#### PLTR：ドル建て ↓0.2% / 円建て ↓1.1%（$196.75）" in out
        assert "- 決算が予想を上回った。" in out
        assert "旧本文" not in out
        # NVDA was configured but not returned: still listed, with real figures.
        assert "#### NVDA：ドル建て ↑1.0% / 円建て ↑0.1%（$100.00）" in out
        assert "### 参考記事" in out and "セクター結果" in out
        assert looks_like_briefing(out)

    def test_call_uses_schema_with_tickers_pinned_and_bounded_retries(self):
        _, calls = self._run([self._payload()])
        schema = calls["kwargs"]["json_schema"]
        assert schema["$defs"]["HoldingNote"]["properties"]["ticker"]["enum"] == ["PLTR", "NVDA"]
        assert calls["kwargs"]["max_attempts"] == RETRY_MAX_ATTEMPTS_BRIEFING

    def test_validation_failure_retries_once_with_the_error(self):
        out, calls = self._run([self._payload(source_ids=("s9",)), self._payload()])
        assert len(calls["holdings"]) == 2
        assert "s9" in calls["holdings"][1]
        assert "#### PLTR：ドル建て" in out

    _FALLBACK_NOTE = "- 〔未確認〕本日の示唆は生成できませんでした。"

    def _assert_quote_only_fallback(self, out):
        # #511: the main analysis no longer writes holdings, so the fallback is
        # the quote-derived headings plus an explicit note, not its Markdown.
        assert "旧本文" not in out
        assert "#### PLTR：ドル建て ↓0.2% / 円建て ↓1.1%（$196.75）" in out
        assert "#### NVDA：ドル建て ↑1.0% / 円建て ↑0.1%（$100.00）" in out
        assert out.count(self._FALLBACK_NOTE) == 2

    def test_exhausted_validation_falls_back_to_quote_only_headings(self):
        bad = self._payload(ticker="TSLA")
        with patch("src.generator.briefing.logger") as log:
            out, calls = self._run([bad, bad])
        assert len(calls["holdings"]) == 2
        self._assert_quote_only_fallback(out)
        assert any("falling back" in c.args[0] for c in log.warning.call_args_list)
        assert "### 参考記事" in out

    def test_non_json_output_falls_back_to_quote_only_headings(self):
        out, _ = self._run(["not json", "still not json"])
        self._assert_quote_only_fallback(out)

    def test_cli_failure_falls_back_without_validation_retry(self):
        out, calls = self._run([RuntimeError("claude CLI timed out (保有銘柄示唆)")])
        assert len(calls["holdings"]) == 1
        self._assert_quote_only_fallback(out)

    def test_no_quotes_skips_briefscript_call_and_keeps_main_markdown(self):
        out, calls = self._run([], quotes=None)
        assert calls["holdings"] == []
        assert "旧本文（Markdown フォールバック）" in out

    def _main_prompt(self, quotes):
        captured = {}

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                captured["prompt"] = prompt
                return self._main(kwargs)
            return self._payload() if label == "保有銘柄示唆" else _SECTORS_OK

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            generate_briefing("x", self._config(), quotes=quotes)
        return captured["prompt"]

    def test_briefscript_mode_main_prompt_drops_holdings_body_and_research(self):
        prompt = self._main_prompt(self._quotes())
        assert "保有者として今日意識すべきこと" not in prompt
        assert "保有・注目銘柄の最新ニュース" not in prompt
        assert "銘柄別示唆" not in prompt and "示唆を書くとき" not in prompt
        assert "保有銘柄の個別の示唆は書かない" in prompt
        assert "PLTR, NVDA" in prompt
        # The few-shot's holdings body is replaced too, or it would model the old output.
        assert "規制の本命銘柄" not in prompt
        assert "### 今日のサマリー（1文）" in prompt

    def test_markdown_mode_main_prompt_keeps_holdings_format(self):
        prompt = self._main_prompt(None)
        assert "保有者として今日意識すべきこと" in prompt
        assert "保有・注目銘柄の最新ニュース: PLTR, NVDA" in prompt
        assert "示唆を書くときは円建てを基準にし" in prompt
        assert "（$123.53）" in prompt
        assert "規制の本命銘柄" in prompt

    def test_padded_and_duplicate_config_tickers_are_normalised(self):
        captured = {}

        def mock(prompt, label, timeout, **kwargs):
            if label == "保有銘柄示唆":
                captured["schema"] = kwargs["json_schema"]
                return self._payload()
            return self._main(kwargs) if label == "メイン分析" else _SECTORS_OK

        config = _make_config(portfolio=PortfolioConfig(tickers=[" PLTR ", "PLTR", "NVDA"], themes=["AI"]))
        with patch("src.generator.briefing.run_claude", side_effect=mock):
            out = generate_briefing("x", config, quotes=self._quotes(), fx_change_pct=-0.9)
        assert captured["schema"]["$defs"]["HoldingNote"]["properties"]["ticker"]["enum"] == ["PLTR", "NVDA"]
        assert out.count("#### PLTR：") == 1


class TestBriefingDocument:
    """generate_briefing_document returns the IR that generate_briefing renders (#513)."""

    def _run(self, holdings, quotes=True, sectors_fail=False):
        from src.generator.briefing import generate_briefing_document

        def mock(prompt, label, timeout, **kwargs):
            if label == "メイン分析":
                return TestBriefScriptHoldings._main(kwargs)
            if label == "セクタースイープ":
                if sectors_fail:
                    raise RuntimeError("sec boom")
                return _SECTORS_OK
            if isinstance(holdings, Exception):
                raise holdings
            return holdings

        config = _make_config(portfolio=PortfolioConfig(tickers=[" PLTR ", "NVDA"], themes=["AI"]))
        q = TestBriefScriptHoldings._quotes() if quotes else None
        with patch("src.generator.briefing.run_claude", side_effect=mock):
            return generate_briefing_document("x", config, quotes=q, fx_change_pct=-0.9)

    def test_holdings_are_a_structured_block_inside_the_main_block(self):
        doc = self._run(TestBriefScriptHoldings._payload())
        kinds = [s.kind for s in doc.sections]
        assert kinds == ["main", "markdown", "sectors"]
        block = doc.sections[0].holdings
        assert block.tickers == ["PLTR", "NVDA"]
        assert block.content.holdings[0].claims[0].text == "決算が予想を上回った。"
        assert {q.ticker for q in doc.market.quotes} == {"PLTR", "NVDA"}
        assert doc.market.fx_change_pct == -0.9

    def test_failed_holdings_call_leaves_an_empty_block(self):
        doc = self._run(RuntimeError("boom"))
        assert doc.sections[0].holdings.content is None

    def test_no_quotes_means_no_holdings_block(self):
        doc = self._run(None, quotes=False)
        assert [s.kind for s in doc.sections][0] == "markdown"
        assert doc.market.quotes == []

    def test_sectors_failure_still_marks_the_rendered_body_degraded(self):
        from src.generator.briefscript_render import render_document_markdown

        doc = self._run(TestBriefScriptHoldings._payload(), sectors_fail=True)
        assert is_degraded_briefing(render_document_markdown(doc))

    def test_document_json_round_trip_renders_the_same_briefing(self):
        from src.generator.briefscript_render import render_document_markdown
        from src.generator.briefscript_schema import BriefingDocument

        doc = self._run(TestBriefScriptHoldings._payload())
        again = BriefingDocument.model_validate_json(doc.model_dump_json())
        assert render_document_markdown(again) == render_document_markdown(doc)


class TestSectorsBriefScript:
    """The sector sweep is generated as validated BriefScript (#514)."""

    def _config(self):
        return _make_config(watch_sectors=[
            WatchSector(sector="AI・クラウド", tickers=["MSFT"]),
            WatchSector(sector=" 防衛 ", tickers=["RTX"]),
        ])

    def _payload(self, sector="AI・クラウド", source_ids=("s1",), extra=()):
        return json.dumps({
            "sectors": [
                {"sector": sector, "claims": [
                    {"text": "データセンター投資の上方修正が続いた。", "confidence": "confirmed",
                     "source_ids": list(source_ids)},
                ], "related_tickers": ["MSFT", "[x](https://evil.example)"]},
                *extra,
            ],
            "sources": [{"id": "s1", "title": "t", "url": "https://example.com/s1"}],
        }, ensure_ascii=False)

    def _run(self, responses):
        calls = []
        it = iter(responses)

        def mock(prompt, label, timeout, **kwargs):
            if label != "セクタースイープ":
                return "### 見出し\n\n" + "本文。" * 80
            calls.append((prompt, kwargs))
            item = next(it)
            if isinstance(item, Exception):
                raise item
            return item

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            out = generate_briefing("x", self._config())
        return out, calls

    def test_every_configured_sector_rendered_once_in_order(self):
        quiet = {"sector": "防衛", "claims": []}
        out, calls = self._run([self._payload(extra=(quiet,))])
        assert out.count("#### AI・クラウド") == 1 and out.count("#### 防衛") == 1
        assert out.index("#### AI・クラウド") < out.index("#### 防衛")
        assert "#### 防衛\n- 動き限定的" in out
        assert "- データセンター投資の上方修正が続いた。［1］" in out
        assert "- ［1］[t](https://example.com/s1)" in out

    def test_sector_missing_from_output_is_marked_unconfirmed(self):
        out, _ = self._run([self._payload()])
        assert "#### 防衛\n- 〔未確認〕今日の動きは確認できませんでした。" in out

    def test_schema_pins_configured_sector_names(self):
        _, calls = self._run([self._payload()])
        schema = calls[0][1]["json_schema"]
        assert schema["$defs"]["SectorNote"]["properties"]["sector"]["enum"] == ["AI・クラウド", "防衛"]
        assert calls[0][1]["max_attempts"] == RETRY_MAX_ATTEMPTS_BRIEFING

    def test_unknown_sector_is_retried_once_with_the_error(self):
        out, calls = self._run([self._payload(sector="宇宙"), self._payload()])
        assert len(calls) == 2 and "宇宙" in calls[1][0]
        assert "#### AI・クラウド" in out

    def test_unknown_source_id_is_retried_once(self):
        out, calls = self._run([self._payload(source_ids=("s9",)), self._payload()])
        assert len(calls) == 2 and "s9" in calls[1][0]

    def test_exhausted_validation_degrades_to_the_recoverable_notice(self):
        out, calls = self._run(["not json", self._payload(sector="宇宙")])
        assert len(calls) == 2
        assert is_degraded_briefing(out) and SECTORS_FAILED_NOTICE in out

    def test_related_tickers_are_sanitised(self):
        out, _ = self._run([self._payload()])
        assert "evil.example" not in out
        assert "- 関連銘柄：MSFT, x" in out

    def test_cli_failure_is_not_validation_retried(self):
        out, calls = self._run([RuntimeError("claude CLI timed out (セクタースイープ)")])
        assert len(calls) == 1 and SECTORS_FAILED_NOTICE in out


class TestMainBriefScript:
    """The main analysis as validated BriefScript when quotes exist (#515)."""

    _FX = "- USD/JPY: 150.23（前日比 +0.10%）"

    def _run(self, main_responses, fx=_FX):
        from src.generator.briefing import generate_briefing_document

        calls = {"main": [], "kwargs": None}
        responses = iter(main_responses)

        def mock(prompt, label, timeout, **kwargs):
            if label == "セクタースイープ":
                return _SECTORS_LONG
            if label == "保有銘柄示唆":
                return TestBriefScriptHoldings._payload()
            calls["main"].append(prompt)
            calls["kwargs"] = kwargs
            calls["timeout"] = timeout
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

        with patch("src.generator.briefing.run_claude", side_effect=mock):
            doc = generate_briefing_document(
                "x", TestBriefScriptHoldings()._config(), fx,
                quotes=TestBriefScriptHoldings._quotes(), fx_change_pct=-0.9,
            )
        return doc, calls

    def test_main_call_uses_the_json_prompt_and_schema(self):
        from src.constants import TIMEOUT_BRIEFING_MAIN

        doc, calls = self._run([_MAIN_OK])
        assert "summary" in calls["kwargs"]["json_schema"]["properties"]
        assert calls["kwargs"]["max_attempts"] == RETRY_MAX_ATTEMPTS_BRIEFING
        assert "出力は指定された JSON スキーマに従うこと" in calls["main"][0]
        assert self._FX in calls["main"][0]
        assert doc.sections[0].kind == "main"
        assert calls["timeout"] == TIMEOUT_BRIEFING_MAIN

    def test_fx_shown_is_the_fetcher_value_even_if_the_model_writes_another(self):
        from src.generator.briefscript_render import render_document_markdown

        rogue_field = _main_json(fx={"rate": 160.0, "claims": []})
        rogue_text = _main_json(fx={"claims": [{"text": "ドル円は 160.00 円。", "confidence": "inferred"}]})
        doc, calls = self._run([rogue_field, rogue_text])
        assert len(calls["main"]) == 2 and "rate" in calls["main"][1]
        out = render_document_markdown(doc)
        assert f"### 為替\n\n{self._FX}\n" in out
        assert doc.market.fx_context == self._FX

    def test_confirmed_claim_without_source_is_retried(self):
        bare = _main_json(stories=[{"title": "T", "claims": [{"text": "x", "confidence": "confirmed"}]}])
        doc, calls = self._run([bare, _MAIN_OK])
        assert len(calls["main"]) == 2 and "must cite at least one source" in calls["main"][1]
        assert doc.sections[0].content.sources[0].id == "s1"

    def test_exhausted_validation_degrades_to_sectors_only(self):
        from src.generator.briefing import MAIN_FAILED_NOTICE, looks_like_briefing_document
        from src.generator.briefscript_render import render_document_markdown

        doc, calls = self._run(["not json", "still not json"])
        assert len(calls["main"]) == 2
        out = render_document_markdown(doc)
        assert out.startswith(MAIN_FAILED_NOTICE) and is_degraded_briefing(out)
        assert "セクター本文" in out and looks_like_briefing_document(doc)

    def test_layout_puts_holdings_and_references_inside_the_main_block(self):
        from src.generator.briefscript_render import render_document_markdown

        out = render_document_markdown(self._run([_MAIN_OK])[0])
        order = ["### 今日のサマリー（1文）", "### 為替", "### 自分への示唆", "#### PLTR：ドル建て",
                 "### 参考記事", "## セクター動向"]
        positions = [out.index(part) for part in order]
        assert positions == sorted(positions)


class TestLooksLikeBriefingDocument:
    def test_validated_main_block_passes_without_the_text_heuristic(self):
        from src.generator.briefing import looks_like_briefing_document
        from src.generator.briefscript_schema import BriefingDocument, MainBlock, parse_main_section

        doc = BriefingDocument(date="2026-10-25", sections=[
            MainBlock(content=parse_main_section(json.loads(_MAIN_OK))),
        ])
        assert looks_like_briefing_document(doc)

    def test_markdown_body_still_uses_the_heuristic(self):
        from src.generator.briefing import looks_like_briefing_document
        from src.generator.briefscript_schema import BriefingDocument, MarkdownSection

        def doc(text):
            return BriefingDocument(date="2026-10-25", sections=[MarkdownSection(text=text)])

        assert not looks_like_briefing_document(doc(HIJACKED_SKILL_COMPLETION_REPORT))
        assert looks_like_briefing_document(doc("### 見出し\n\n" + "本文。" * 100))
