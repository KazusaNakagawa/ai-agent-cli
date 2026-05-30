import pytest
from pydantic import ValidationError

from web.schemas import BriefingConfigSchema, PortfolioSchema, WatchSectorSchema


def test_valid_briefing_config():
    config = BriefingConfigSchema(
        portfolio=PortfolioSchema(tickers=["PLTR"], themes=["AI"]),
        watch_sectors=[
            WatchSectorSchema(sector="AI & Cloud", tickers=["NVDA"], notes=None),
        ],
        geopolitical={"conflicts": []},
        watch_events=[],
    )
    assert config.portfolio.tickers == ["PLTR"]


def test_watch_sector_rejects_empty_tickers():
    with pytest.raises(ValidationError):
        WatchSectorSchema(sector="AI", tickers=[])


def test_portfolio_rejects_empty_tickers():
    with pytest.raises(ValidationError):
        PortfolioSchema(tickers=[], themes=["AI"])


def test_briefing_config_requires_at_least_one_watch_sector():
    with pytest.raises(ValidationError):
        BriefingConfigSchema(
            portfolio=PortfolioSchema(tickers=["PLTR"], themes=["AI"]),
            watch_sectors=[],
            geopolitical={"conflicts": []},
            watch_events=[],
        )
