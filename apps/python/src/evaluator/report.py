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


_TARGET_TOP_N = 10

_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2.5rem 1.5rem;
  font-family: -apple-system, "Hiragino Sans", "Segoe UI", system-ui, sans-serif;
  background: #0f1115; color: #e6e8ec; line-height: 1.5;
}
.wrap { max-width: 880px; margin: 0 auto; }
h1 { font-size: 1.7rem; font-weight: 700; letter-spacing: .02em; margin: 0 0 .25rem; }
.sub { color: #8b93a1; font-size: .85rem; margin-bottom: 2rem; }
.card {
  background: #171a21; border: 1px solid #232732; border-radius: 14px;
  padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.4);
}
.card h2 { font-size: 1.05rem; margin: 0 0 1rem; display: flex; gap: .5rem; align-items: baseline; }
.card h2 .note { font-size: .75rem; color: #8b93a1; font-weight: 400; }
table { width: 100%; border-collapse: collapse; }
td { padding: .45rem .5rem; border-top: 1px solid #232732; vertical-align: middle; }
tr:first-child td { border-top: none; }
.label { font-weight: 600; white-space: nowrap; }
.num { color: #aeb6c2; font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.bar { background: #232732; border-radius: 6px; height: 14px; width: 100%; overflow: hidden; }
.bar .fill { height: 100%; border-radius: 6px; transition: width .3s; }
"""


def _color(rate: float) -> str:
    # hit率 0=赤 → 1=緑 へ連続変化（hue 0→120）。
    hue = int(round(rate * 120))
    return f"hsl({hue}, 65%, 48%)"


def _bar_html(rate: float) -> str:
    pct = round(rate * 100)
    return (f'<div class="bar"><div class="fill" '
            f'style="width:{pct}%;background:{_color(rate)}"></div></div>')


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _section_rows(rates: dict[str, dict], top_n: int | None = None) -> str:
    items = sorted(rates.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["hit_rate"]))
    if top_n is not None:
        items = items[:top_n]
    return "\n".join(
        f'<tr><td class="label">{_esc(k)}</td>'
        f'<td class="num">{v["count"]}</td>'
        f'<td class="num">{v["hit_rate"]:.2f}</td>'
        f'<td>{_bar_html(v["hit_rate"])}</td></tr>'
        for k, v in items
    )


def _trend_rows(by_date: list[dict]) -> str:
    return "\n".join(
        f'<tr><td class="label">{_esc(d["date"])}</td>'
        f'<td class="num">{d["hit_rate"]:.2f}</td>'
        f'<td>{_bar_html(d["hit_rate"])}</td></tr>'
        for d in by_date
    )


def _card(title: str, body: str, note: str = "") -> str:
    note_html = f'<span class="note">{_esc(note)}</span>' if note else ""
    return (f'<section class="card"><h2>{_esc(title)}{note_html}</h2>'
            f'<table>{body}</table></section>')


def build_report() -> str:
    claims_by_id: dict[str, dict] = {}
    for f in sorted(storage.CLAIMS_DIR.glob("*.json")):
        for c in storage.load_json(f):
            claims_by_id[c["id"]] = c
    scores: list[dict] = []
    for f in sorted(storage.SCORES_DIR.glob("*.json")):
        scores.extend(storage.load_json(f))
    agg = aggregate(scores, claims_by_id)

    target_count = len(agg["by_target"])
    target_note = (f"上位 {_TARGET_TOP_N} 件 / 全 {target_count} 件"
                   if target_count > _TARGET_TOP_N else "")
    cards = "\n".join([
        _card("type別 hit率", _section_rows(agg["by_type"])),
        _card("セクター/銘柄別 hit率",
              _section_rows(agg["by_target"], top_n=_TARGET_TOP_N), target_note),
        _card("hit率の推移", _trend_rows(agg["by_date"])),
    ])
    html = (
        "<!doctype html>\n"
        '<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>ブリーフィング評価スコアカード</title>"
        f"<style>{_CSS}</style></head><body><div class=\"wrap\">"
        "<h1>ブリーフィング評価スコアカード</h1>"
        '<div class="sub">後日のブリーフィングを真値とした的中率（hit=1.0 / partial=0.5 / miss=0）</div>'
        f"{cards}</div></body></html>\n"
    )
    storage.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    storage.REPORT_PATH.write_text(html, encoding="utf-8")
    return html
