from __future__ import annotations

import json
import re

from src.claude_runner import run_claude
from src.evaluator import storage
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)

_VALID_DIRECTION = {"強気", "弱気", "中立"}
_VALID_TYPE = {"prediction", "causal"}
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_array(raw: str) -> list:
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("eval-extract: JSON parse failed, treating as empty")
        return []
    return data if isinstance(data, list) else []


def _normalize_targets(value) -> list[str]:
    # Wrap in a list before normalizing so a single string from the LLM is not split into chars.
    if not isinstance(value, list):
        value = [value] if str(value).strip() else []
    return [str(t) for t in value if str(t).strip()]


def _to_int(value, default: int) -> int:
    # Fall back to the default so a non-numeric/type-mismatched horizon_days does not break extraction.
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_claims(raw: str, date_str: str) -> list[dict]:
    claims = []
    for i, item in enumerate(_extract_json_array(raw), start=1):
        if not isinstance(item, dict):
            continue
        direction = item.get("direction")
        ctype = item.get("type")
        if direction not in _VALID_DIRECTION or ctype not in _VALID_TYPE:
            continue
        claims.append({
            "id": f"{date_str}-{i:02d}",
            "theme": str(item.get("theme", "")).strip(),
            "direction": direction,
            "targets": _normalize_targets(item.get("targets", [])),
            "horizon_days": _to_int(item.get("horizon_days") or 5, 5),
            "type": ctype,
        })
    return claims


def extract_one(date_str: str) -> list[dict]:
    body = storage.briefing_path(date_str).read_text(encoding="utf-8")
    prompt = render("eval_extract", briefing=body)
    raw = run_claude(prompt, label=f"eval-extract {date_str}")
    claims = parse_claims(raw, date_str)
    storage.save_json(storage.CLAIMS_DIR / f"{date_str}.json", claims)
    return claims


def extract(target: str = "all") -> None:
    dates = storage.list_briefing_dates() if target == "all" else [target]
    for date_str in dates:
        if (storage.CLAIMS_DIR / f"{date_str}.json").exists():
            logger.info("eval-extract: %s already extracted, skipping", date_str)
            continue
        extract_one(date_str)
