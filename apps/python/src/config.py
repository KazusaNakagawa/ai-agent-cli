"""Module that loads briefing.json and xss_intel.json.

The briefing config schema is defined once as Pydantic v2 models and shared by
both ``/api/config`` and ``load_config()``. Inheritance structure:

- ``BriefingFileConfig`` — the part writable in ``briefing.json`` (publishable).
  Re-exported from ``web.schemas`` as ``BriefingConfigSchema`` for the
  ``/api/config`` input/output schema.
- ``BriefingConfig`` — extends ``BriefingFileConfig`` with the 4 credential
  fields injected from env. Runtime consumers (handler / generator / notifier)
  receive this one.

Input validation (non-empty ``tickers`` / ``watch_sectors``, etc.) is
consolidated in Pydantic. ``load_config()`` wraps ``pydantic.ValidationError``
in ``ValueError`` to keep the public contract.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.credentials import get_credential
from src.logger import get_logger

logger = get_logger(__name__)

# Load the repo-root .env first (two levels up from apps/python/).
# Since credentials.get_credential() prefers values already in the keychain,
# .env acts as the fallback when a key is not registered in the keychain.
load_dotenv(Path(__file__).parents[2] / ".env")

CONFIG_PATH = Path(os.getenv("BRIEFING_CONFIG_PATH", str(Path(__file__).parents[1] / "config" / "briefing.json")))
XSS_INTEL_CONFIG_PATH = Path(__file__).parents[1] / "config" / "xss_intel.json"


class Conflict(BaseModel):
    name: str
    affected_sectors: list[str]
    related_tickers: list[str] = Field(default_factory=list)
    notes: str | None = None
    # English search query for the local-LLM path pre-fetch (#153). Searching by
    # Japanese topic name tends to hit standing index pages, so prefer this when set.
    query_en: str | None = None


class GeopoliticalConfig(BaseModel):
    conflicts: list[Conflict] = Field(default_factory=list)


class PortfolioConfig(BaseModel):
    tickers: list[str] = Field(min_length=1)
    themes: list[str]


class WatchSector(BaseModel):
    sector: str
    tickers: list[str] = Field(min_length=1)
    notes: str | None = None


class WatchEvent(BaseModel):
    name: str
    trigger: str
    affected_sectors: list[str]
    related_tickers: list[str] = Field(default_factory=list)
    notes: str | None = None


class ObsidianConfig(BaseModel):
    """Optional Obsidian vault integration settings (journal sync + chat RAG)."""

    model_config = ConfigDict(extra="forbid")

    vault_path: str
    journal_subdir: str = "journal"
    exclude_dirs: list[str] = Field(
        default_factory=lambda: [".obsidian", ".trash", "templates"]
    )


class JournalChatConfig(BaseModel):
    """Journal chat settings (#414).

    ``trusted_write_dirs`` lists directories the Journal brainstorm chat is
    allowed to write to without an interactive permission prompt (the ``claude``
    CLI denies writes outside its default scope outright in headless ``-p``
    mode — there is no prompt to approve later). Empty by default so existing
    installs see unchanged (no elevated write access) behavior.
    """

    model_config = ConfigDict(extra="forbid")

    trusted_write_dirs: list[str] = Field(default_factory=list)


class BriefingFileConfig(BaseModel):
    """The part expressed in ``briefing.json``. Contains no credentials.

    Shaped so it can be used directly and safely as ``/api/config`` input/output.
    ``extra="forbid"`` rejects briefing.json typos (e.g. ``watch_evens``) at load
    time instead of silently dropping them."""

    model_config = ConfigDict(extra="forbid")

    # Model ID passed to the claude CLI (optional). DEFAULT_MODEL if unset.
    # Precedence: CLAUDE_MODEL env > this config value > DEFAULT_MODEL (see claude_runner.get_model).
    model: str | None = None
    portfolio: PortfolioConfig
    geopolitical: GeopoliticalConfig = Field(default_factory=GeopoliticalConfig)
    watch_sectors: list[WatchSector] = Field(min_length=1)
    watch_events: list[WatchEvent] = Field(default_factory=list)
    # Optional Obsidian vault integration. None = feature disabled.
    obsidian: ObsidianConfig | None = None
    journal_chat: JournalChatConfig = Field(default_factory=JournalChatConfig)


class BriefingConfig(BriefingFileConfig):
    """For runtime use: the file part + credentials via env.

    The inheritance order matters: because it extends ``BriefingFileConfig``
    (the file shape), narrowing to the ``BriefingFileConfig`` view when passing
    to the API ensures secrets do not leak."""

    discord_token: str = ""
    discord_channel_id: str = ""
    notion_api_key: str = ""
    notion_database_id: str = ""


def load_config() -> BriefingConfig:
    """Build and return a BriefingConfig from briefing.json and env vars.

    Pydantic's ``ValidationError`` is wrapped in ``ValueError`` for backward
    compatibility — existing callers (the CLI startup path that calls load_config
    directly, tests/test_config.py) expect ``ValueError``. The error message
    extracts only the first violation into an "at <loc>: <msg>" form (Pydantic's
    default full stringification is hard to read as a startup log)."""
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    try:
        return BriefingConfig(
            **raw,
            discord_token=get_credential("DISCORD_TOKEN") or "",
            discord_channel_id=get_credential("CHANNEL_ID") or "",
            notion_api_key=get_credential("NOTION_API_KEY") or "",
            notion_database_id=get_credential("NOTION_DATABASE_ID") or "",
        )
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(x) for x in first["loc"])
        raise ValueError(
            f"briefing.json validation failed at {loc}: {first['msg']}"
        ) from e


def get_journal_notion_credentials() -> tuple[str, str]:
    """Return (api_key, database_id) for Journal <-> Notion sync.

    Unlike CONFIG, this reads credentials directly and does not require
    briefing.json to exist — Journal sync is independent of the briefing batch.
    """
    return (
        get_credential("NOTION_API_KEY") or "",
        get_credential("NOTION_DATABASE_ID_JOURNAL") or "",
    )


def get_obsidian_config() -> ObsidianConfig | None:
    """Return the ``obsidian`` section of briefing.json, or None when disabled.

    Best-effort by design: a missing briefing.json, a validation error, or an
    absent ``obsidian`` section all mean "feature off" — callers (journal sync,
    chat RAG, CLI) must not fail because of Obsidian configuration. A missing
    file is expected (briefing.json is optional, see CLAUDE.md), so only
    unexpected errors (e.g. a validation error in an existing file) are logged.
    """
    try:
        return load_config().obsidian
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("get_obsidian_config: briefing.json could not be loaded", exc_info=True)
        return None


def get_journal_chat_trusted_write_dirs() -> list[str]:
    """Return Journal chat's trusted write directories, ``~`` expanded.

    Best-effort like ``get_obsidian_config()``: a missing briefing.json or a
    validation error both mean "nothing trusted yet" (empty list), which
    matches the claude CLI's existing default-deny behavior for writes
    outside its scope — callers must not fail because of this optional config.
    """
    try:
        dirs = load_config().journal_chat.trusted_write_dirs
    except FileNotFoundError:
        return []
    except (ValueError, json.JSONDecodeError):
        # ValueError covers load_config()'s wrapped ValidationError;
        # JSONDecodeError (a ValueError subclass) covers malformed JSON.
        logger.warning(
            "get_journal_chat_trusted_write_dirs: briefing.json could not be loaded",
            exc_info=True,
        )
        return []
    return [str(Path(d).expanduser()) for d in dirs]


_CONFIG_CACHE: BriefingConfig | None = None


def __getattr__(name: str) -> BriefingConfig:
    """Lazy-evaluate ``CONFIG`` on first attribute access (PEP 562).

    Importing ``src.config`` no longer reads ``briefing.json`` at module-load
    time. The FastAPI web server can boot before that file exists — which is
    the whole point of ``/api/config`` (the operator manages the file via the
    API). Batch jobs that actually dereference ``CONFIG.portfolio`` etc. still
    hit ``FileNotFoundError`` at first access if the file is missing, which is
    the correct behavior for them — the briefing can't run without it.
    """
    if name == "CONFIG":
        global _CONFIG_CACHE
        if _CONFIG_CACHE is None:
            _CONFIG_CACHE = load_config()
        return _CONFIG_CACHE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# XSS configs stay as dataclasses intentionally — they have no /api/config
# counterpart so the Pydantic schema-sharing argument doesn't apply.
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
    """Build and return an XssIntelConfig from xss_intel.json and env vars."""
    raw = json.loads(XSS_INTEL_CONFIG_PATH.read_text(encoding="utf-8"))
    targets = XssTargetsConfig(**raw["targets"])

    return XssIntelConfig(
        targets=targets,
        discord_token=get_credential("DISCORD_TOKEN") or "",
        discord_channel_id=get_credential("CHANNEL_ID") or "",
        notion_api_key=get_credential("NOTION_API_KEY") or "",
        notion_database_id=get_credential("NOTION_DATABASE_ID") or "",
    )


_XSS_CONFIG: XssIntelConfig | None = None


def get_xss_config() -> XssIntelConfig:
    """Return XssIntelConfig as a singleton (loaded only on first access)."""
    global _XSS_CONFIG
    if _XSS_CONFIG is None:
        _XSS_CONFIG = load_xss_config()
    return _XSS_CONFIG
