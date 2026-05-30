"""briefing.json と xss_intel.json をロードするモジュール。

ブリーフィングの設定スキーマは Pydantic v2 モデルで 1 箇所に定義し、
``/api/config`` と ``load_config()`` の両方で共有する。継承構造:

- ``BriefingFileConfig`` — ``briefing.json`` に書ける部分（公開可能）。
  ``/api/config`` の input/output スキーマとして ``web.schemas`` から
  ``BriefingConfigSchema`` の名前で re-export される。
- ``BriefingConfig`` — ``BriefingFileConfig`` を継承し、env から注入する
  クレデンシャル 4 フィールドを足す。ランタイム消費者 (handler / generator /
  notifier) はこちらを受け取る。

入力バリデーション (``tickers`` / ``watch_sectors`` の non-empty 等) は
Pydantic 側で集約。``load_config()`` は ``pydantic.ValidationError`` を
``ValueError`` にラップして公開コントラクトを維持する。
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

CONFIG_PATH = Path(os.getenv("BRIEFING_CONFIG_PATH", str(Path(__file__).parents[1] / "config" / "briefing.json")))
XSS_INTEL_CONFIG_PATH = Path(__file__).parents[1] / "config" / "xss_intel.json"


class Conflict(BaseModel):
    name: str
    affected_sectors: list[str]
    related_tickers: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class GeopoliticalConfig(BaseModel):
    conflicts: list[Conflict] = Field(default_factory=list)


class PortfolioConfig(BaseModel):
    tickers: list[str] = Field(min_length=1)
    themes: list[str]


class WatchSector(BaseModel):
    sector: str
    tickers: list[str] = Field(min_length=1)
    notes: Optional[str] = None


class WatchEvent(BaseModel):
    name: str
    trigger: str
    affected_sectors: list[str]
    related_tickers: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class BriefingFileConfig(BaseModel):
    """``briefing.json`` で表現される部分。クレデンシャルは含まない。

    ``/api/config`` の input/output として直接安全に使える形にしてある。"""

    portfolio: PortfolioConfig
    geopolitical: GeopoliticalConfig = Field(default_factory=GeopoliticalConfig)
    watch_sectors: list[WatchSector] = Field(min_length=1)
    watch_events: list[WatchEvent] = Field(default_factory=list)


class BriefingConfig(BriefingFileConfig):
    """ランタイム用。ファイル部分 + env 経由のクレデンシャル。

    継承順がポイント: ``BriefingFileConfig`` (file shape) を拡張する形なので、
    API 側に渡すときは ``BriefingFileConfig`` 視点に絞り込めば secrets は漏れない。"""

    discord_token: str = ""
    discord_channel_id: str = ""
    notion_api_key: str = ""
    notion_database_id: str = ""


def load_config() -> BriefingConfig:
    """briefing.json と環境変数から BriefingConfig を構築して返す。

    Pydantic の ``ValidationError`` は ``ValueError`` にラップする — 既存の
    呼び出し側 (load_config を直接叩く CLI 起動パス、tests/test_config.py) が
    ``ValueError`` を期待しているための後方互換。"""
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    try:
        return BriefingConfig(
            **raw,
            discord_token=os.getenv("DISCORD_TOKEN", ""),
            discord_channel_id=os.getenv("CHANNEL_ID", ""),
            notion_api_key=os.getenv("NOTION_API_KEY", ""),
            notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
        )
    except ValidationError as e:
        raise ValueError(f"briefing.json validation failed: {e}") from e


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
    """xss_intel.json と環境変数から XssIntelConfig を構築して返す。"""
    raw = json.loads(XSS_INTEL_CONFIG_PATH.read_text(encoding="utf-8"))
    targets = XssTargetsConfig(**raw["targets"])

    return XssIntelConfig(
        targets=targets,
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        discord_channel_id=os.getenv("CHANNEL_ID", ""),
        notion_api_key=os.getenv("NOTION_API_KEY", ""),
        notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
    )


_XSS_CONFIG: Optional[XssIntelConfig] = None


def get_xss_config() -> XssIntelConfig:
    """XssIntelConfig をシングルトンとして返す（初回アクセス時にのみ読み込む）。"""
    global _XSS_CONFIG
    if _XSS_CONFIG is None:
        _XSS_CONFIG = load_xss_config()
    return _XSS_CONFIG
