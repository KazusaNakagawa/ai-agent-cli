"""OS Keychain ラッパ + .env フォールバック。

`python-keyring` 経由で OS のキーチェーンに資格情報を保存する。読み出し時に
キーチェーンが ``None`` を返した場合のみ、同名の環境変数にフォールバックする。
書き込みは常にキーチェーンへ行う（.env は不変）。

許可された名前 (`ALLOWED_KEYS`) 以外は ``ValueError``。これは
``/api/credentials`` の入力サニタイズと、運用ミスでよく分からないキーが
保管されないようにするためのガード。
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
