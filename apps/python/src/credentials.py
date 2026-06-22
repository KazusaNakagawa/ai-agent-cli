"""OS Keychain wrapper + .env fallback.

Stores credentials in the OS keychain via `python-keyring`. On read, falls back
to the same-named environment variable only when the keychain returns ``None``.
Writes always go to the keychain (.env is immutable).

Names outside the allowed set (`ALLOWED_KEYS`) raise ``ValueError``. This guards
both the ``/api/credentials`` input sanitization and against operational
mistakes that would store unknown keys.
"""
import os
from typing import Any

import keyring

SERVICE = "ai-agent"
ALLOWED_KEYS: tuple[str, ...] = (
    "DISCORD_TOKEN",
    "CHANNEL_ID",
    "NOTION_API_KEY",
    "NOTION_DATABASE_ID",
    "ANTHROPIC_API_KEY",
)

_backend: Any = keyring


def _ensure_allowed(name: str) -> None:
    if name not in ALLOWED_KEYS:
        raise ValueError(f"Unknown credential key: {name}")


def get_credential(name: str) -> str | None:
    _ensure_allowed(name)
    try:
        value = _backend.get_password(SERVICE, name)
    except keyring.errors.NoKeyringError:
        value = None
    if value:
        return value
    return os.environ.get(name) or None


def set_credential(name: str, value: str) -> None:
    _ensure_allowed(name)
    _backend.set_password(SERVICE, name, value)


def delete_credential(name: str) -> None:
    _ensure_allowed(name)
    _backend.delete_password(SERVICE, name)


def list_credentials() -> dict[str, bool]:
    return {name: get_credential(name) is not None for name in ALLOWED_KEYS}
