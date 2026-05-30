"""API 境界の Pydantic v2 スキーマ。src.config のデータクラスを変更せず、JSON ⇔ dict 変換を担う。"""
from pydantic import BaseModel, Field


class ConflictSchema(BaseModel):
    name: str
    affected_sectors: list[str]
    related_tickers: list[str] = Field(default_factory=list)
    notes: str | None = None


class GeopoliticalSchema(BaseModel):
    conflicts: list[ConflictSchema] = Field(default_factory=list)


class PortfolioSchema(BaseModel):
    tickers: list[str] = Field(min_length=1)
    themes: list[str]


class WatchSectorSchema(BaseModel):
    sector: str
    tickers: list[str] = Field(min_length=1)
    notes: str | None = None


class WatchEventSchema(BaseModel):
    name: str
    trigger: str
    affected_sectors: list[str]
    related_tickers: list[str] = Field(default_factory=list)
    notes: str | None = None


class BriefingConfigSchema(BaseModel):
    portfolio: PortfolioSchema
    geopolitical: GeopoliticalSchema = Field(default_factory=GeopoliticalSchema)
    watch_sectors: list[WatchSectorSchema] = Field(min_length=1)
    watch_events: list[WatchEventSchema] = Field(default_factory=list)
