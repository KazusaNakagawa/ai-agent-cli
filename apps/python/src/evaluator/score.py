from __future__ import annotations

import json
import re
from datetime import date, timedelta
from itertools import groupby

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
        "confidence": _to_float(data.get("confidence"), 0.0),
        "rationale": str(data.get("rationale", "")),
    }


def parse_verdicts_batch(raw: str) -> list[dict] | None:
    """Parse a batch response (JSON array). Return None on failure.

    Return None if even one element is not a dict, to trigger the fallback.
    The id is overwritten position-based by the caller, so store the raw value here.
    """
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return None
    except (json.JSONDecodeError, TypeError):
        return None
    results = []
    for item in data:
        if not isinstance(item, dict):
            return None
        verdict = item.get("verdict", "unresolved")
        if verdict not in _VALID_VERDICT:
            verdict = "unresolved"
        results.append({
            "id": item.get("id"),  # finalized position-based by the caller
            "verdict": verdict,
            "confidence": _to_float(item.get("confidence"), 0.0),
            "rationale": str(item.get("rationale", "")),
        })
    return results


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def score_claim(claim: dict, all_dates: list[str]) -> dict:
    """Score a single claim. Internally goes through score_claims_batch."""
    results = score_claims_batch([claim], all_dates)
    return results[0]


def score_claims_batch(
    claims: list[dict],
    all_dates: list[str],
    precomputed: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Score claims in the same followup group with a single LLM call.

    precomputed: a precomputed {claim_id: followup_dates} map. When passed,
    skips recomputing followup_dates().
    Fallback: if the batch response fails to parse, re-run per-claim.
    """
    # Resolve followup_dates
    followup_map: dict[str, list[str]] = precomputed if precomputed is not None else {
        c["id"]: followup_dates(c["id"][:10], c["horizon_days"], all_dates)
        for c in claims
    }

    # Claims with no followups are resolved immediately here
    resolved: list[dict] = []
    pending: list[dict] = []
    for c in claims:
        if not followup_map[c["id"]]:
            resolved.append({"id": c["id"], "verdict": "unresolved", "confidence": 0.0,
                              "rationale": "no follow-up briefing in window"})
        else:
            pending.append(c)

    if not pending:
        return resolved

    # Build the union of followup bodies (joined via a set to dedupe within the group)
    all_followup_dates: list[str] = sorted(
        {d for c in pending for d in followup_map[c["id"]]}
    )
    bodies = "\n\n---\n\n".join(
        storage.briefing_path(d).read_text(encoding="utf-8") for d in all_followup_dates
    )
    themes_json = json.dumps(
        [{"id": c["id"], "theme": c.get("theme", ""), "direction": c.get("direction", ""),
          "targets": c.get("targets", []), "horizon_days": c.get("horizon_days", 0),
          "type": c.get("type", "")}
         for c in pending],
        ensure_ascii=False,
    )

    base_date = pending[0]["id"][:10]
    label = f"eval-judge {base_date} ({len(pending)} claims)"
    prompt = render("eval_judge", themes=themes_json, followups=bodies)
    raw = run_claude(prompt, label=label)

    batch_results = parse_verdicts_batch(raw)
    if batch_results is not None and len(batch_results) == len(pending):
        # Do not trust the LLM's id; finalize pending ids position-based
        for result, claim in zip(batch_results, pending):
            result["id"] = claim["id"]
        return resolved + batch_results

    # Fallback: if the batch response was broken, re-run one claim at a time
    logger.warning(
        "eval-judge batch response parse failed (%s), running per-claim fallback", base_date,
    )
    fallback = []
    for c in pending:
        fup_dates = followup_map[c["id"]]
        fup_bodies = "\n\n---\n\n".join(
            storage.briefing_path(d).read_text(encoding="utf-8") for d in fup_dates
        )
        single_themes = json.dumps(
            [{"id": c["id"], "theme": c.get("theme", ""), "direction": c.get("direction", ""),
              "targets": c.get("targets", []), "horizon_days": c.get("horizon_days", 0),
              "type": c.get("type", "")}],
            ensure_ascii=False,
        )
        single_prompt = render("eval_judge", themes=single_themes, followups=fup_bodies)
        single_raw = run_claude(single_prompt, label=f"eval-judge {c['id']}")
        single_results = parse_verdicts_batch(single_raw)
        if single_results and len(single_results) == 1:
            single_results[0]["id"] = c["id"]  # finalize id position-based
            fallback.append(single_results[0])
        else:
            fallback.append({"id": c["id"], "verdict": "unresolved", "confidence": 0.0,
                             "rationale": "parse error"})
    return resolved + fallback


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

        # Split into finalized and pending
        finalized: list[dict] = []
        pending: list[dict] = []
        for claim in claims:
            prev = existing.get(claim["id"])
            if prev and prev["verdict"] != "unresolved":
                finalized.append(prev)
            else:
                pending.append(claim)

        if not pending:
            storage.save_json(scores_file, finalized)
            continue

        # Compute followup_dates once and cache it, reused for grouping and batching
        followups_cache: dict[str, list[str]] = {
            c["id"]: followup_dates(c["id"][:10], c["horizon_days"], all_dates)
            for c in pending
        }

        def _key(c: dict) -> tuple[str, ...]:
            return tuple(followups_cache[c["id"]])

        pending.sort(key=_key)
        batch_results: list[dict] = []
        for _, group in groupby(pending, key=_key):
            claims_in_group = list(group)
            group_cache = {c["id"]: followups_cache[c["id"]] for c in claims_in_group}
            batch_results.extend(score_claims_batch(claims_in_group, all_dates, group_cache))

        # Save in the original claim order
        id_to_result = {r["id"]: r for r in finalized + batch_results}
        results = [id_to_result[c["id"]] for c in claims if c["id"] in id_to_result]
        storage.save_json(scores_file, results)
