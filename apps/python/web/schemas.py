"""API 境界のスキーマ。

historical な ``*Schema`` 名で ``src.config`` の Pydantic モデルを re-export する。
スキーマの真の定義は `src/config.py` 側にある — そちらが ``load_config()`` の
入力検証と ``/api/config`` の I/O 検証の両方を担う。
"""
from src.config import (
    BriefingFileConfig as BriefingConfigSchema,
    Conflict as ConflictSchema,
    GeopoliticalConfig as GeopoliticalSchema,
    PortfolioConfig as PortfolioSchema,
    WatchEvent as WatchEventSchema,
    WatchSector as WatchSectorSchema,
)

__all__ = [
    "BriefingConfigSchema",
    "ConflictSchema",
    "GeopoliticalSchema",
    "PortfolioSchema",
    "WatchEventSchema",
    "WatchSectorSchema",
]
