from datetime import datetime

import pytest

from src.config import BriefingConfig, GeopoliticalConfig, PortfolioConfig, WatchSector
from src.local_llm.briefing import (
    build_local_briefing_prompt,
    compose_briefing_md,
    generate_local_briefing,
)


def _minimal_cfg() -> BriefingConfig:
    # watch_sectors requires min_length=1; portfolio.tickers requires min_length=1
    return BriefingConfig(
        portfolio=PortfolioConfig(tickers=["PLTR", "NVDA"], themes=["AI", "半導体"]),
        watch_sectors=[WatchSector(sector="AI & Cloud", tickers=["NVDA"])],
        geopolitical=GeopoliticalConfig(),
        watch_events=[],
        discord_token="",
        discord_channel_id="",
        notion_api_key="",
        notion_database_id="",
    )


def test_build_local_briefing_prompt_inserts_inputs():
    cfg = _minimal_cfg()
    out = build_local_briefing_prompt(cfg, stocks="PLTR +2.1%\nNVDA +0.5%")

    assert "AI" in out
    assert "半導体" in out
    assert "PLTR" in out
    assert "NVDA" in out
    assert "PLTR +2.1%" in out
    assert "WebSearch" not in out  # local prompt removes the WebSearch instruction


class FakeOllama:
    def __init__(self, tokens, captured=None):
        self._tokens = tokens
        self._captured = captured if captured is not None else {}

    def generate(self, model, prompt, stream):
        assert stream is True
        self._captured["model"] = model
        self._captured["prompt"] = prompt
        for t in self._tokens:
            yield {"response": t, "done": False}
        yield {"response": "", "done": True}


def test_generate_local_briefing_collects_stream(capsys):
    captured: dict = {}
    olm = FakeOllama(tokens=["Hel", "lo ", "世界"], captured=captured)

    full = generate_local_briefing("PROMPT", ollama_client=olm, model="qwen2.5:7b")

    assert full == "Hello 世界"
    assert captured["model"] == "qwen2.5:7b"
    assert captured["prompt"] == "PROMPT"
    assert "Hello 世界" in capsys.readouterr().out


def test_compose_briefing_md_emits_caveat_then_body():
    md = compose_briefing_md(
        body="### 今日のサマリー\n本文\n",
        model="qwen2.5:7b",
        generated_at=datetime(2026, 6, 8, 9, 15, 0),
    )

    head, _, body = md.partition("\n\n---\n\n")
    assert "ローカル LLM" in head
    assert "qwen2.5:7b" in head
    assert "WebSearch 未使用" in head
    assert "2026-06-08T09:15:00" in head
    assert body.startswith("### 今日のサマリー")
