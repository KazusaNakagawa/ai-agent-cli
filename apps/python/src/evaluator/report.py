from __future__ import annotations

from collections import defaultdict

from src.evaluator import storage

_WEIGHT = {"hit": 1.0, "partial": 0.5, "miss": 0.0}


def _weight(verdict: str) -> float:
    return _WEIGHT[verdict]


def _rate(bucket: list[float]) -> dict:
    return {"count": len(bucket), "hit_rate": round(sum(bucket) / len(bucket), 4)}


def aggregate(scores: list[dict], claims_by_id: dict[str, dict]) -> dict:
    by_type: dict[str, list[float]] = defaultdict(list)
    by_target: dict[str, list[float]] = defaultdict(list)
    by_date: dict[str, list[float]] = defaultdict(list)
    for s in scores:
        if s["verdict"] not in _WEIGHT:  # unresolved / unknown
            continue
        claim = claims_by_id.get(s["id"])
        if claim is None:
            continue
        w = _weight(s["verdict"])
        by_type[claim["type"]].append(w)
        by_date[s["id"][:10]].append(w)
        for t in claim["targets"]:
            by_target[t].append(w)
    return {
        "by_type": {k: _rate(v) for k, v in by_type.items()},
        "by_target": {k: _rate(v) for k, v in by_target.items()},
        "by_date": [{"date": d, "hit_rate": _rate(by_date[d])["hit_rate"]}
                    for d in sorted(by_date)],
    }


def pie_block(title: str, rates: dict[str, dict]) -> str:
    lines = ["```mermaid", f"pie title {title} (hit率)"]
    for k, v in rates.items():
        lines.append(f'    "{k}" : {v["hit_rate"]}')
    lines.append("```")
    return "\n".join(lines)


def xychart_block(by_date: list[dict]) -> str:
    xs = ", ".join(f'"{d["date"]}"' for d in by_date)
    ys = ", ".join(str(d["hit_rate"]) for d in by_date)
    return "\n".join([
        "```mermaid",
        "xychart-beta",
        '    title "hit率の推移"',
        f"    x-axis [{xs}]",
        '    y-axis "hit率" 0 --> 1',
        f"    line [{ys}]",
        "```",
    ])


def _table(title: str, rates: dict[str, dict]) -> str:
    rows = [f"| {k} | {v['count']} | {v['hit_rate']} |" for k, v in rates.items()]
    return "\n".join([f"#### {title}", "| 区分 | 件数 | hit率 |", "|---|---|---|", *rows])


def build_report() -> str:
    claims_by_id: dict[str, dict] = {}
    for f in sorted(storage.CLAIMS_DIR.glob("*.json")):
        for c in storage.load_json(f):
            claims_by_id[c["id"]] = c
    scores: list[dict] = []
    for f in sorted(storage.SCORES_DIR.glob("*.json")):
        scores.extend(storage.load_json(f))
    agg = aggregate(scores, claims_by_id)
    parts = [
        "# ブリーフィング評価スコアカード",
        "## type別", pie_block("type別", agg["by_type"]), _table("type別", agg["by_type"]),
        "## セクター/銘柄別", pie_block("target別", agg["by_target"]),
        _table("target別", agg["by_target"]),
        "## 時系列", xychart_block(agg["by_date"]),
    ]
    report_md = "\n\n".join(parts) + "\n"
    storage.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    storage.REPORT_PATH.write_text(report_md, encoding="utf-8")
    return report_md
