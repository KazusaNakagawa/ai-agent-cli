import pytest
from pydantic import ValidationError

from src.config import BriefingConfig
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


def test_api_surface_does_not_include_credential_fields():
    """Inheritance direction guard: BriefingFileConfig (= BriefingConfigSchema)
    is the parent of BriefingConfig. If a future refactor flips that so file-
    config inherits from BriefingConfig, the four credential fields would
    silently leak through GET /api/config. This catches that at test time."""
    secret_fields = {
        "discord_token",
        "discord_channel_id",
        "notion_api_key",
        "notion_database_id",
    }
    assert secret_fields.isdisjoint(BriefingConfigSchema.model_fields)
    # Sanity: BriefingConfig (runtime view) DOES have them.
    assert secret_fields.issubset(BriefingConfig.model_fields)


def test_briefing_config_rejects_unknown_fields():
    """extra='forbid' catches operator typos in briefing.json such as
    'watch_evens' (s/v/) — without this, silently dropped to an empty list."""
    with pytest.raises(ValidationError):
        BriefingConfigSchema(
            portfolio=PortfolioSchema(tickers=["PLTR"], themes=["AI"]),
            watch_sectors=[WatchSectorSchema(sector="AI", tickers=["NVDA"], notes=None)],
            geopolitical={"conflicts": []},
            watch_events=[],
            watch_evens=[],  # typo
        )
