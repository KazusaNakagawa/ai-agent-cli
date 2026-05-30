import os
from pathlib import Path

# テスト実行時は tests/config/briefing.json を使用し、本番設定を読まない
os.environ.setdefault("BRIEFING_CONFIG_PATH", str(Path(__file__).parent / "config" / "briefing.json"))
