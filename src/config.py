import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parents[1] / "config" / "briefing.json"


@dataclass
class Conflict:
    name: str
    affected_sectors: list[str]
    related_tickers: list[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass
class GeopoliticalConfig:
    conflicts: list[Conflict] = field(default_factory=list)


@dataclass
class PortfolioConfig:
    tickers: list[str]
    themes: list[str]


@dataclass
class BriefingConfig:
    portfolio: PortfolioConfig
    geopolitical: GeopoliticalConfig = field(default_factory=GeopoliticalConfig)
    discord_token: str = ""
    discord_channel_id: str = ""


def load_config() -> BriefingConfig:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    portfolio = PortfolioConfig(**raw["portfolio"])

    conflicts = [Conflict(**c) for c in raw["geopolitical"]["conflicts"]]
    geopolitical = GeopoliticalConfig(conflicts=conflicts)

    return BriefingConfig(
        portfolio=portfolio,
        geopolitical=geopolitical,
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        discord_channel_id=os.getenv("CHANNEL_ID", ""),
    )


CONFIG = load_config()
