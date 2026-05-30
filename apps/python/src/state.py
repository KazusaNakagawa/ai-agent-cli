"""``~/.ai-agent/state.json`` の読み書き。

ホストごとの非機密ランタイム状態。資格情報は Keychain (``src.credentials``)、
ユーザー設定 (portfolio 等) は ``apps/python/config/briefing.json``、
このファイルは「オンボーディング済みか」「auth_mode は cli か api か」
といった runtime トグル専用。
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

STATE_FILE = Path.home() / ".ai-agent" / "state.json"
ALLOWED_AUTH_MODES: tuple[str, ...] = ("cli", "api")


@dataclass
class State:
    onboarded: bool = False
    auth_mode: Literal["cli", "api"] = "cli"
    migrated_from_env: bool = False
    version: int = 1


def read_state() -> State:
    if not STATE_FILE.exists():
        return State()
    raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return State(
        onboarded=raw.get("onboarded", False),
        auth_mode=raw.get("auth_mode", "cli"),
        migrated_from_env=raw.get("migrated_from_env", False),
        version=raw.get("version", 1),
    )


def write_state(state: State) -> None:
    if state.auth_mode not in ALLOWED_AUTH_MODES:
        raise ValueError(f"Invalid auth_mode: {state.auth_mode}")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
