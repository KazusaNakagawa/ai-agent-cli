from datetime import datetime
from pathlib import Path

import pytest

from src.config import BriefingConfig, GeopoliticalConfig, PortfolioConfig, WatchSector
from src.local_llm import cli
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
    # watch_sectors is intentionally not rendered (Claude-only scope).
    assert "AI & Cloud" not in out


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


class _FakeRunCLI:
    """Helper for cli._cmd_briefing tests: monkeypatches the four collaborators."""

    def __init__(self, monkeypatch, tmp_path, *, briefing_text="### 今日\nbody\n"):
        self.notion_calls: list[dict] = []
        self.output_dir = tmp_path / "out"
        self.output_dir.mkdir()

        monkeypatch.setattr(cli, "BRIEFING_OUTPUT_DIR", self.output_dir)
        monkeypatch.setattr(cli, "fetch_stock_moves", lambda tickers: "PLTR +1%")
        monkeypatch.setattr(
            cli, "load_briefing_config", lambda: _minimal_cfg()
        )
        monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
        monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
        monkeypatch.setattr(
            cli,
            "build_local_briefing_prompt",
            lambda cfg, stocks: "PROMPT",
        )
        monkeypatch.setattr(
            cli,
            "generate_local_briefing",
            lambda prompt, *, ollama_client, model: briefing_text,
        )

        def _fake_notion(text, api_key, db_id, *, title, tags=None, extra_properties=None):
            self.notion_calls.append({"text": text, "title": title, "tags": tags})
            return "https://www.notion.so/fake"

        monkeypatch.setattr(cli, "send_to_notion", _fake_notion)


def _cfg_with_notion() -> BriefingConfig:
    return _minimal_cfg().model_copy(update={
        "notion_api_key": "k",
        "notion_database_id": "d",
    })


def test_cmd_briefing_writes_local_file_and_skips_notion(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    files = list(fake.output_dir.glob("local_*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "ローカル LLM" in content
    assert "### 今日" in content
    assert fake.notion_calls == []


def test_cmd_briefing_posts_to_notion_when_flag(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "load_briefing_config", _cfg_with_notion)

    rc = cli.main(["--briefing", "--notion", "--root", str(tmp_path)])

    assert rc == 0
    assert len(fake.notion_calls) == 1
    call = fake.notion_calls[0]
    assert "ローカルブリーフィング" in call["title"]
    assert "local" in (call["tags"] or [])
    assert "agent" in (call["tags"] or [])


def test_cmd_briefing_notion_without_flag_is_noop(monkeypatch, tmp_path):
    """--notion 未指定なら NOTION_API_KEY が揃っていても投稿しない。"""
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "load_briefing_config", _cfg_with_notion)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    assert fake.notion_calls == []
