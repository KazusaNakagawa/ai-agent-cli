"""Tests for the Claude API briefing cost-verification spike (#204)."""

import pytest

from src.generator import briefing_api
from src.local_llm.briefing.prefetch import PrefetchedContext
from src.local_llm.search import SearchResult


def _ctx_with_one_macro_hit() -> PrefetchedContext:
    hit = SearchResult(
        title="NVDA jumps on AI demand",
        url="https://example.com/nvda",
        description="short snippet",
        content="Full article body about NVDA and AI capex.",
    )
    return PrefetchedContext(
        macro=[hit], per_ticker={}, geo_by_topic={}, events_by_name={}
    )


def test_compute_cost_usd_matches_sonnet_pricing():
    usage = {
        "input_tokens": 1000,
        "output_tokens": 1000,
        "cache_creation_input_tokens": 1000,
        "cache_read_input_tokens": 1000,
    }
    # Sonnet per-Mtok: input 3 + output 15 + cache-write 3.75 + cache-read 0.30
    expected = (3.0 + 15.0 + 3.75 + 0.30) * 1000 / 1_000_000
    assert briefing_api.compute_cost_usd(usage) == pytest.approx(expected)


def test_compute_cost_usd_tolerates_missing_keys():
    assert briefing_api.compute_cost_usd({"output_tokens": 2000}) == pytest.approx(
        15.0 * 2000 / 1_000_000
    )


def test_build_context_block_includes_hit_fields():
    block = briefing_api.build_context_block(_ctx_with_one_macro_hit())
    assert "NVDA jumps on AI demand" in block
    assert "https://example.com/nvda" in block
    assert "Full article body about NVDA" in block


def test_build_api_prompts_injects_context_and_omits_websearch():
    ctx = _ctx_with_one_macro_hit()
    main_prompt, sectors_prompt = briefing_api.build_api_prompts(
        themes="AI",
        tickers="NVDA",
        geopolitical="(none)",
        watch_events="(none)",
        watch_sectors="(none)",
        stocks="NVDA +1%",
        few_shot="(example)",
        context_block=briefing_api.build_context_block(ctx),
    )
    # Context is injected, and the CLI-only WebSearch instruction is gone.
    assert "https://example.com/nvda" in main_prompt
    assert "WebSearch" not in main_prompt
    assert "WebSearch" not in sectors_prompt
    assert "NVDA" in sectors_prompt


class _FakeMessage:
    def __init__(self):
        self.content = [type("Block", (), {"text": "生成された本文"})()]
        self.usage = type(
            "Usage",
            (),
            {
                "input_tokens": 100,
                "output_tokens": 200,
                "cache_creation_input_tokens": 300,
                "cache_read_input_tokens": 400,
            },
        )()


class _FakeMessages:
    def __init__(self, recorder):
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.append(kwargs)
        return _FakeMessage()


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.messages = _FakeMessages(self.calls)


def test_generate_section_calls_sonnet_without_tools():
    client = _FakeClient()
    text, usage = briefing_api.generate_section(
        client, system="sys", prompt="hello"
    )
    assert text == "生成された本文"
    assert usage["output_tokens"] == 200
    call = client.calls[0]
    assert call["model"] == briefing_api.SONNET_MODEL == "claude-sonnet-4-6"
    assert "tools" not in call  # no tools on the API path
    assert call["system"] == "sys"


def test_log_section_usage_logs_with_api_label(monkeypatch):
    recorded = {}

    def fake_log_usage(label, usage, cost_usd, duration_ms):
        recorded["label"] = label
        recorded["usage"] = usage
        recorded["cost_usd"] = cost_usd

    monkeypatch.setattr(briefing_api, "log_usage", fake_log_usage)
    usage = {
        "input_tokens": 0,
        "output_tokens": 1000,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    briefing_api.log_section_usage("メイン分析(API)", usage, duration_ms=123)
    assert recorded["label"] == "メイン分析(API)"
    assert recorded["cost_usd"] == pytest.approx(15.0 * 1000 / 1_000_000)
