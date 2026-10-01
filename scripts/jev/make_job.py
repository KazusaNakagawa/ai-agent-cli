"""Build job.json for compare.mjs from the evaluator's local output.

Samples scored claims, attaches the follow-up briefing bodies that eval-judge
would have seen, and records the baseline verdict produced by run_claude.
Follow-up text is truncated to CAP characters because Jev caps the state at
32,000 tokens; see README.md.

Usage (from repo root):
    python3 scripts/jev/make_job.py [sample_size]
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

CAP = 20_000  # characters of follow-up text kept per claim
SEED = 42

REPO = Path(__file__).resolve().parents[2]
# Mirrors apps/python/src/paths.resolve_data_home(): BRIEF_LENS_HOME wins when set.
_home = os.environ.get("BRIEF_LENS_HOME", "").strip()
DATA_HOME = Path(_home).expanduser().resolve() if _home else REPO / "apps/python"
EVAL = DATA_HOME / "output/eval"
BRIEF = DATA_HOME / "output/briefing"
OUT = Path(__file__).resolve().parent / "job.json"

_BRIEFING_RE = re.compile(r"^briefing_(\d{4}-\d{2}-\d{2})\.md$")


def briefing_dates() -> list[str]:
    return sorted(m.group(1) for p in BRIEF.iterdir() if (m := _BRIEFING_RE.match(p.name)))


def followup_dates(base: str, horizon: int, all_dates: list[str]) -> list[str]:
    lo = date.fromisoformat(base)
    hi = lo + timedelta(days=horizon)
    return [d for d in all_dates if lo < date.fromisoformat(d) <= hi]


def main() -> None:
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    for d in (EVAL, BRIEF):
        if not d.is_dir():
            sys.exit(f"missing {d}: run the briefing and evaluator first, or set BRIEF_LENS_HOME")
    all_dates = briefing_dates()
    bodies: dict[str, str] = {}

    def body(d: str) -> str:
        if d not in bodies:
            bodies[d] = (BRIEF / f"briefing_{d}.md").read_text(encoding="utf-8")
        return bodies[d]

    rows = []
    for scores_file in sorted((EVAL / "scores").glob("*.json")):
        claims_file = EVAL / "claims" / f"{scores_file.stem}.json"
        if not claims_file.exists():
            continue
        scores = {s["id"]: s for s in json.loads(scores_file.read_text(encoding="utf-8"))}
        for claim in json.loads(claims_file.read_text(encoding="utf-8")):
            score = scores.get(claim["id"])
            if not score or score["verdict"] == "unresolved":
                continue
            dates = followup_dates(claim["id"][:10], claim["horizon_days"], all_dates)
            if not dates:
                continue
            full = "\n\n---\n\n".join(body(d) for d in dates)
            rows.append({
                "id": claim["id"],
                "theme": claim["theme"],
                "direction": claim["direction"],
                "targets": claim["targets"],
                "horizon_days": claim["horizon_days"],
                "type": claim["type"],
                "followups_full_chars": len(full),
                "followups": full[:CAP],
                "truncated": len(full) > CAP,
                "baseline_verdict": score["verdict"],
                "baseline_confidence": score["confidence"],
            })

    if not rows:
        sys.exit(f"no eligible claims under {EVAL} (need scored, resolved claims with follow-up briefings in {BRIEF})")

    random.seed(SEED)
    sample = random.sample(rows, min(sample_size, len(rows)))
    OUT.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")

    sizes = sorted(r["followups_full_chars"] for r in rows)
    print(f"pool {len(rows)} claims, sampled {len(sample)} -> {OUT}")
    print(f"full follow-up chars: min={sizes[0]} median={sizes[len(sizes) // 2]} max={sizes[-1]}")
    print("baseline:", dict(Counter(r["baseline_verdict"] for r in sample)))
    print("truncated:", sum(r["truncated"] for r in sample), "/", len(sample))


if __name__ == "__main__":
    main()
