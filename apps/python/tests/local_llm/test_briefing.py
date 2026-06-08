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
