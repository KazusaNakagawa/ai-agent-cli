from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from src.constants import BRIEFING_OUTPUT_DIR, OUTPUT_DIR

EVAL_DIR = OUTPUT_DIR / "eval"
CLAIMS_DIR = EVAL_DIR / "claims"
SCORES_DIR = EVAL_DIR / "scores"
REPORT_DIR = EVAL_DIR / "reports"
REPORT_PATH = EVAL_DIR / "report.html"  # 最新レポート（常に上書き）


def dated_report_path(date_str: str) -> Path:
    return REPORT_DIR / f"report_{date_str}.html"

_BRIEFING_RE = re.compile(r"^briefing_(\d{4}-\d{2}-\d{2})\.md$")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def briefing_path(date_str: str) -> Path:
    return BRIEFING_OUTPUT_DIR / f"briefing_{date_str}.md"


def list_briefing_dates() -> list[str]:
    if not BRIEFING_OUTPUT_DIR.exists():
        return []
    dates: list[str] = []
    for p in BRIEFING_OUTPUT_DIR.iterdir():
        m = _BRIEFING_RE.match(p.name)
        if not m:
            continue
        d = m.group(1)
        try:
            date.fromisoformat(d)  # 形式は合うが暦上無効な日付を除外
        except ValueError:
            continue
        dates.append(d)
    return sorted(dates)
