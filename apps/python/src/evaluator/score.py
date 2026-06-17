from __future__ import annotations

import json
import re
from datetime import date, timedelta

from src.claude_runner import run_claude
from src.evaluator import storage
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)

_VALID_VERDICT = {"hit", "miss", "partial", "unresolved"}
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def followup_dates(base: str, horizon: int, all_dates: list[str]) -> list[str]:
    lo = date.fromisoformat(base)
    hi = lo + timedelta(days=horizon)
    return [d for d in all_dates if lo < date.fromisoformat(d) <= hi]


def parse_verdict(raw: str) -> dict:
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        verdict = data["verdict"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"verdict": "unresolved", "confidence": 0.0, "rationale": "parse error"}
    if verdict not in _VALID_VERDICT:
        return {"verdict": "unresolved", "confidence": 0.0, "rationale": "unknown verdict"}
    return {
        "verdict": verdict,
        "confidence": float(data.get("confidence", 0.0)),
        "rationale": str(data.get("rationale", "")),
    }


def score_claim(claim: dict, all_dates: list[str]) -> dict:
    followups = followup_dates(claim["id"][:10], claim["horizon_days"], all_dates)
    if not followups:
        return {"id": claim["id"], "verdict": "unresolved", "confidence": 0.0,
                "rationale": "no follow-up briefing in window"}
    bodies = "\n\n---\n\n".join(
        storage.briefing_path(d).read_text(encoding="utf-8") for d in followups
    )
    theme = json.dumps(claim, ensure_ascii=False)
    prompt = render("eval_judge", theme=theme, followups=bodies)
    raw = run_claude(prompt, label=f"eval-judge {claim['id']}")
    return {"id": claim["id"], **parse_verdict(raw)}


def score(target: str = "all") -> None:
    all_dates = storage.list_briefing_dates()
    dates = all_dates if target == "all" else [target]
    for date_str in dates:
        claims_file = storage.CLAIMS_DIR / f"{date_str}.json"
        if not claims_file.exists():
            continue
        claims = storage.load_json(claims_file)
        scores_file = storage.SCORES_DIR / f"{date_str}.json"
        existing = {s["id"]: s for s in storage.load_json(scores_file)} \
            if scores_file.exists() else {}
        results = []
        for claim in claims:
            prev = existing.get(claim["id"])
            if prev and prev["verdict"] != "unresolved":
                results.append(prev)  # idempotent: keep finalized
                continue
            results.append(score_claim(claim, all_dates))
        storage.save_json(scores_file, results)
