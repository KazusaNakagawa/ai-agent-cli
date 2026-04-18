import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parents[1] / "config" / "briefing.json"
XSS_INTEL_CONFIG_PATH = Path(__file__).parents[1] / "config" / "xss_intel.json"


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
class WatchSector:
    sector: str
    tickers: list[str]
    notes: Optional[str] = None


@dataclass
class BriefingConfig:
    portfolio: PortfolioConfig
    geopolitical: GeopoliticalConfig = field(default_factory=GeopoliticalConfig)
    watch_sectors: list[WatchSector] = field(default_factory=list)
    discord_token: str = ""
    discord_channel_id: str = ""
    notion_api_key: str = ""
    notion_database_id: str = ""


def load_config() -> BriefingConfig:
    """briefing.json と環境変数から BriefingConfig を構築して返す。"""
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    portfolio = PortfolioConfig(**raw["portfolio"])

    conflicts = [Conflict(**c) for c in raw["geopolitical"]["conflicts"]]
    geopolitical = GeopoliticalConfig(conflicts=conflicts)

    raw_watch_sectors = raw.get("watch_sectors")
    if not raw_watch_sectors:
        raise ValueError("briefing.json の watch_sectors が未設定です")

    watch_sectors = [WatchSector(**s) for s in raw_watch_sectors]
    empty_ticker_sectors = [s.sector for s in watch_sectors if not s.tickers]
    if empty_ticker_sectors:
        raise ValueError(
            "watch_sectors に tickers が空のセクターがあります: "
            + ", ".join(empty_ticker_sectors)
        )

    return BriefingConfig(
        portfolio=portfolio,
        geopolitical=geopolitical,
        watch_sectors=watch_sectors,
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        discord_channel_id=os.getenv("CHANNEL_ID", ""),
        notion_api_key=os.getenv("NOTION_API_KEY", ""),
        notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
    )


CONFIG = load_config()


@dataclass
class XssTargetsConfig:
    frameworks: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class XssIntelConfig:
    targets: XssTargetsConfig = field(default_factory=XssTargetsConfig)
    discord_token: str = ""
    discord_channel_id: str = ""
    notion_api_key: str = ""
    notion_database_id: str = ""


def load_xss_config() -> XssIntelConfig:
    """xss_intel.json と環境変数から XssIntelConfig を構築して返す。必須変数が未設定の場合は ValueError を送出する。"""
    raw = json.loads(XSS_INTEL_CONFIG_PATH.read_text(encoding="utf-8"))
    targets = XssTargetsConfig(**raw["targets"])

    required = {
        "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN", ""),
        "CHANNEL_ID": os.getenv("CHANNEL_ID", ""),
        "NOTION_API_KEY": os.getenv("NOTION_API_KEY", ""),
        "NOTION_DATABASE_ID": os.getenv("NOTION_DATABASE_ID", ""),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"必須環境変数が未設定です: {', '.join(missing)}")

    return XssIntelConfig(
        targets=targets,
        discord_token=required["DISCORD_TOKEN"],
        discord_channel_id=required["CHANNEL_ID"],
        notion_api_key=required["NOTION_API_KEY"],
        notion_database_id=required["NOTION_DATABASE_ID"],
    )


_XSS_CONFIG: Optional[XssIntelConfig] = None


def get_xss_config() -> XssIntelConfig:
    """XssIntelConfig をシングルトンとして返す（初回アクセス時にのみ読み込む）。"""
    global _XSS_CONFIG
    if _XSS_CONFIG is None:
        _XSS_CONFIG = load_xss_config()
    return _XSS_CONFIG
