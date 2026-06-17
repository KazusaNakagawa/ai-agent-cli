# Briefing Evaluation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 過去のブリーフィングからテーマを構造化抽出し、後日のブリーフィングを真値として LLM-as-judge で採点、的中率を Mermaid 付きマークダウンで集計する評価基盤を作る。

**Architecture:** `apps/python/src/evaluator/` に分離した3ステップのパイプライン（extract → score → report）。各ステップは独立に実行・テスト可能。LLM 呼び出しは全て `src.claude_runner.run_claude`（CLI=サブスク経路）。永続化は `output/eval/` 配下の JSON、レポートは Mermaid 埋め込みマークダウン。

**Tech Stack:** Python 3.13, pytest, 既存 `run_claude` / `src.generator.prompt.render` / pandas（既存依存、集計に利用）。新規ライブラリ追加なし。

## Global Constraints

- LLM 呼び出しは必ず `from src.claude_runner import run_claude` を経由する。`subprocess.run(["claude", ...])` を直接書かない。
- プロンプトは `apps/python/prompts/*.md` に置き、`src.generator.prompt.render(template_name, **kwargs)` で読む。テンプレートのプレースホルダは `string.Template` 形式（`$name`）。
- 成果物（`output/eval/**`）はコミットしない。プロンプト `.md` はトラッキングする。
- テストは TDD。`run_claude` をモックして決定的にする。テストは `apps/python/tests/evaluator/` 配下。
- Conventional Commits（`feat:` / `test:` / `chore:`）。コミットメッセージは英語。
- 作業ブランチは `feat/briefing-eval-foundation`（作成済み）。

---

### Task 1: storage モジュール（パスと JSON 入出力）

**Files:**
- Create: `apps/python/src/evaluator/__init__.py`
- Create: `apps/python/src/evaluator/storage.py`
- Test: `apps/python/tests/evaluator/__init__.py`
- Test: `apps/python/tests/evaluator/test_storage.py`

**Interfaces:**
- Consumes: `src.constants.OUTPUT_DIR`, `src.constants.BRIEFING_OUTPUT_DIR`
- Produces:
  - `EVAL_DIR: Path` (= `OUTPUT_DIR / "eval"`), `CLAIMS_DIR: Path`, `SCORES_DIR: Path`, `REPORT_PATH: Path`
  - `save_json(path: Path, data) -> None`
  - `load_json(path: Path) -> Any` (ファイル無しなら `FileNotFoundError`)
  - `briefing_path(date_str: str) -> Path` (= `BRIEFING_OUTPUT_DIR / f"briefing_{date_str}.md"`)
  - `list_briefing_dates() -> list[str]` — `BRIEFING_OUTPUT_DIR` 内の `briefing_YYYY-MM-DD.md` を昇順の `YYYY-MM-DD` 文字列リストで返す（`local_*` や連番サフィックス付きは除外）

- [ ] **Step 1: Write the failing test**

```python
# apps/python/tests/evaluator/test_storage.py
import json
from pathlib import Path

import pytest

from src.evaluator import storage


def test_save_and_load_json_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    storage.save_json(p, {"x": 1})
    assert storage.load_json(p) == {"x": 1}


def test_load_json_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        storage.load_json(tmp_path / "missing.json")


def test_list_briefing_dates_filters_and_sorts(tmp_path, monkeypatch):
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    for name in [
        "briefing_2026-06-17.md",
        "briefing_2026-06-15.md",
        "local_2026-06-16.md",
        "briefing_2026-06-16-001.md",
    ]:
        (bdir / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    assert storage.list_briefing_dates() == ["2026-06-15", "2026-06-17"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.evaluator'`

- [ ] **Step 3: Write minimal implementation**

```python
# apps/python/src/evaluator/__init__.py
"""Briefing evaluation foundation (see docs/.../2026-06-17-briefing-eval-foundation-design.md)."""
```

```python
# apps/python/src/evaluator/storage.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.constants import BRIEFING_OUTPUT_DIR, OUTPUT_DIR

EVAL_DIR = OUTPUT_DIR / "eval"
CLAIMS_DIR = EVAL_DIR / "claims"
SCORES_DIR = EVAL_DIR / "scores"
REPORT_PATH = EVAL_DIR / "report.md"

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
    dates = [
        m.group(1)
        for p in BRIEFING_OUTPUT_DIR.iterdir()
        if (m := _BRIEFING_RE.match(p.name))
    ]
    return sorted(dates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_storage.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/evaluator/__init__.py apps/python/src/evaluator/storage.py apps/python/tests/evaluator/
git commit -m "feat(eval): add evaluator storage paths and json helpers"
```

---

### Task 2: 抽出（テーマ構造化）

**Files:**
- Create: `apps/python/src/evaluator/extract.py`
- Create: `apps/python/prompts/eval_extract.md`
- Test: `apps/python/tests/evaluator/test_extract.py`

**Interfaces:**
- Consumes: `storage.{briefing_path,list_briefing_dates,save_json,load_json,CLAIMS_DIR}`, `src.claude_runner.run_claude`, `src.generator.prompt.render`
- Produces:
  - `parse_claims(raw: str, date_str: str) -> list[dict]` — LLM 生出力（JSON配列、コードフェンス混入可）からテーマを取り出し、各要素に `id = f"{date_str}-{nn:02d}"`（1始まり）を付与。`direction`/`type`/`horizon_days` を検証（欠落時 `horizon_days=5`）。不正 JSON は `[]`。
  - `extract_one(date_str: str) -> list[dict]` — ブリーフィング md を読み、`render("eval_extract", briefing=...)` → `run_claude(prompt, label=f"eval-extract {date_str}")` → `parse_claims`。結果を `CLAIMS_DIR / f"{date_str}.json"` に保存して返す。
  - `extract(target: str = "all") -> None` — `target=="all"` なら `list_briefing_dates()` 全件、それ以外は単一日付。**冪等**: `CLAIMS_DIR/{date}.json` が既存ならスキップ。

各テーマ dict 形: `{"id","theme","direction","targets","horizon_days","type"}`。

- [ ] **Step 1: Write the failing test**

```python
# apps/python/tests/evaluator/test_extract.py
from pathlib import Path
from unittest.mock import patch

from src.evaluator import extract, storage

_LLM_OUT = """```json
[
  {"theme": "高PER株に逆風", "direction": "弱気",
   "targets": ["PLTR", "MSFT"], "horizon_days": 5, "type": "prediction"},
  {"theme": "防衛セクター需要長期化", "direction": "強気",
   "targets": ["NOC"], "type": "causal"}
]
```"""


def test_parse_claims_assigns_ids_and_defaults():
    claims = extract.parse_claims(_LLM_OUT, "2026-06-17")
    assert [c["id"] for c in claims] == ["2026-06-17-01", "2026-06-17-02"]
    assert claims[1]["horizon_days"] == 5  # default applied
    assert claims[0]["type"] == "prediction"


def test_parse_claims_bad_json_returns_empty():
    assert extract.parse_claims("not json at all", "2026-06-17") == []


def test_extract_one_saves_claims(tmp_path, monkeypatch):
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    (bdir / "briefing_2026-06-17.md").write_text("本文", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    monkeypatch.setattr(storage, "CLAIMS_DIR", tmp_path / "claims")
    with patch("src.evaluator.extract.run_claude", return_value=_LLM_OUT):
        claims = extract.extract_one("2026-06-17")
    assert len(claims) == 2
    saved = storage.load_json(tmp_path / "claims" / "2026-06-17.json")
    assert saved == claims
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: module 'src.evaluator.extract'`

- [ ] **Step 3: Write the prompt template**

```markdown
<!-- apps/python/prompts/eval_extract.md -->
以下は投資家向け日次ブリーフィングです。ここからマクロ・テーマ単位の「見立て」を抽出してください。

抽出ルール:
- 各テーマは {theme, direction, targets, horizon_days, type} の JSON オブジェクト。
- direction は "強気" | "弱気" | "中立" のいずれか。
- type は "prediction"（前向きの示唆・予測）| "causal"（地政学などの因果主張）。
- targets はセクター名や銘柄ティッカーの配列。
- horizon_days は検証に妥当な日数（1〜10）。判断できなければ 5。
- 散文の言い換えは避け、検証可能な方向性のあるテーマだけを抽出。
- 出力は JSON 配列のみ。説明文を付けない。

--- ブリーフィング本文 ---
$briefing
```

- [ ] **Step 4: Write minimal implementation**

```python
# apps/python/src/evaluator/extract.py
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
        logger.warning("eval-extract: JSON 解析失敗、空として扱います")
        return []
    return data if isinstance(data, list) else []


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
            "targets": [str(t) for t in item.get("targets", []) if str(t).strip()],
            "horizon_days": int(item.get("horizon_days") or 5),
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
            logger.info("eval-extract: %s は抽出済み、スキップ", date_str)
            continue
        extract_one(date_str)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_extract.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add apps/python/src/evaluator/extract.py apps/python/prompts/eval_extract.md apps/python/tests/evaluator/test_extract.py
git commit -m "feat(eval): extract structured themes from briefings via LLM"
```

---

### Task 3: 採点（LLM-as-judge）

**Files:**
- Create: `apps/python/src/evaluator/score.py`
- Create: `apps/python/prompts/eval_judge.md`
- Test: `apps/python/tests/evaluator/test_score.py`

**Interfaces:**
- Consumes: `storage.{briefing_path,list_briefing_dates,save_json,load_json,CLAIMS_DIR,SCORES_DIR}`, `run_claude`, `render`
- Produces:
  - `followup_dates(base: str, horizon: int, all_dates: list[str]) -> list[str]` — `(base, base+horizon]` の窓に入る後日ブリーフィング日付を返す（`base` 自身は除外、`base+horizon` 含む）。日付比較は `datetime.date.fromisoformat`。
  - `parse_verdict(raw: str) -> dict` — judge の生出力から `{"verdict","confidence","rationale"}` を取り出す。`verdict` が想定外/不正 JSON なら `{"verdict":"unresolved","confidence":0.0,"rationale":"parse error"}`。
  - `score_claim(claim: dict, all_dates: list[str]) -> dict` — 窓内に後日ブリーフィングが無ければ `{"id":..,"verdict":"unresolved",..}`。あれば窓内ブリーフィング本文を結合して `run_claude` で判定。
  - `score(target: str = "all") -> None` — claims を読み、**冪等**: 既存 scores のうち `unresolved` 以外は再採点しない。`unresolved`/未採点だけ採点して `SCORES_DIR/{date}.json` を更新保存。

verdict は `hit|miss|partial|unresolved`。

- [ ] **Step 1: Write the failing test**

```python
# apps/python/tests/evaluator/test_score.py
from unittest.mock import patch

from src.evaluator import score, storage

_DATES = ["2026-06-17", "2026-06-19", "2026-06-25"]


def test_followup_dates_window_inclusive_upper_exclusive_base():
    # base 6-17, horizon 5 -> (6-17, 6-22] -> only 6-19
    assert score.followup_dates("2026-06-17", 5, _DATES) == ["2026-06-19"]


def test_followup_dates_none_when_no_briefing_in_window():
    assert score.followup_dates("2026-06-17", 1, _DATES) == []


def test_parse_verdict_bad_json_is_unresolved():
    v = score.parse_verdict("garbage")
    assert v["verdict"] == "unresolved"


def test_score_claim_unresolved_without_followup(monkeypatch):
    claim = {"id": "2026-06-17-01", "theme": "t", "direction": "弱気",
             "targets": ["PLTR"], "horizon_days": 1, "type": "prediction"}
    result = score.score_claim(claim, _DATES)
    assert result == {"id": "2026-06-17-01", "verdict": "unresolved",
                      "confidence": 0.0, "rationale": "no follow-up briefing in window"}


def test_score_claim_uses_judge_when_followup_exists(tmp_path, monkeypatch):
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    (bdir / "briefing_2026-06-19.md").write_text("後日本文", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    claim = {"id": "2026-06-17-01", "theme": "t", "direction": "弱気",
             "targets": ["PLTR"], "horizon_days": 5, "type": "prediction"}
    judge_out = '{"verdict": "hit", "confidence": 0.7, "rationale": "ok"}'
    with patch("src.evaluator.score.run_claude", return_value=judge_out):
        result = score.score_claim(claim, _DATES)
    assert result["verdict"] == "hit"
    assert result["id"] == "2026-06-17-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_score.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError`

- [ ] **Step 3: Write the prompt template**

```markdown
<!-- apps/python/prompts/eval_judge.md -->
あなたは投資ブリーフィングの見立てを後追い検証する審査員です。

元の見立て（テーマ）:
$theme

検証期間中の後日ブリーフィング（真値）:
$followups

このテーマの方向性が、後日ブリーフィングの記述に照らして妥当だったかを判定してください。
- verdict: "hit"（方向性が当たった）| "miss"（外れた）| "partial"（部分的）| "unresolved"（判断材料不足）
- confidence: 0.0〜1.0
- rationale: 1〜2文の根拠（後日ブリーフィングの記述を引用）
出力は {"verdict","confidence","rationale"} の JSON オブジェクトのみ。
```

- [ ] **Step 4: Write minimal implementation**

```python
# apps/python/src/evaluator/score.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_score.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add apps/python/src/evaluator/score.py apps/python/prompts/eval_judge.md apps/python/tests/evaluator/test_score.py
git commit -m "feat(eval): score themes via LLM-as-judge over follow-up briefings"
```

---

### Task 4: レポート集計と Mermaid 視覚化

**Files:**
- Create: `apps/python/src/evaluator/report.py`
- Test: `apps/python/tests/evaluator/test_report.py`

**Interfaces:**
- Consumes: `storage.{SCORES_DIR,REPORT_PATH,save_json}` 不要、`SCORES_DIR.glob`、`load_json`
- Produces:
  - `_weight(verdict: str) -> float` — `hit=1.0`, `partial=0.5`, `miss=0.0`。`unresolved` は集計対象外。
  - `aggregate(scores: list[dict], claims_by_id: dict[str, dict]) -> dict` — 確定スコア（`unresolved` 除外）を集計し `{"by_type": {...}, "by_target": {...}, "by_date": [...]}` を返す。各値は `{"count": int, "hit_rate": float}`。`by_date` は `[{"date","hit_rate"}]` を日付昇順。
  - `pie_block(title: str, rates: dict[str, dict]) -> str` — Mermaid `pie` 文字列。
  - `xychart_block(by_date: list[dict]) -> str` — Mermaid `xychart-beta` 文字列。
  - `build_report() -> str` — `SCORES_DIR` と `CLAIMS_DIR` を全件読み、Mermaid＋テーブルのマークダウンを組み立て `REPORT_PATH` に書き、本文を返す。

`by_target` は `claims_by_id` 経由で各スコアの `targets` を展開し、target ごとに加重集計。

- [ ] **Step 1: Write the failing test**

```python
# apps/python/tests/evaluator/test_report.py
from src.evaluator import report


def _claim(cid, ctype, targets):
    return {"id": cid, "type": ctype, "targets": targets,
            "theme": "t", "direction": "弱気", "horizon_days": 5}


def test_aggregate_hit_rate_with_partial_weight():
    claims = {
        "d1-01": _claim("d1-01", "prediction", ["PLTR"]),
        "d1-02": _claim("d1-02", "prediction", ["PLTR"]),
        "d1-03": _claim("d1-03", "causal", ["NOC"]),
    }
    scores = [
        {"id": "d1-01", "verdict": "hit"},
        {"id": "d1-02", "verdict": "partial"},
        {"id": "d1-03", "verdict": "unresolved"},  # excluded
    ]
    agg = report.aggregate(scores, claims)
    # prediction: (1.0 + 0.5) / 2 = 0.75 ; causal excluded (unresolved)
    assert agg["by_type"]["prediction"] == {"count": 2, "hit_rate": 0.75}
    assert "causal" not in agg["by_type"]
    assert agg["by_target"]["PLTR"] == {"count": 2, "hit_rate": 0.75}


def test_pie_block_is_mermaid():
    block = report.pie_block("type別", {"prediction": {"count": 2, "hit_rate": 0.75}})
    assert "```mermaid" in block and "pie" in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# apps/python/src/evaluator/report.py
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
    lines = ["```mermaid", f'pie title {title} (hit率)']
    for k, v in rates.items():
        lines.append(f'    "{k}" : {v["hit_rate"]}')
    lines.append("```")
    return "\n".join(lines)


def xychart_block(by_date: list[dict]) -> str:
    xs = ", ".join(d["date"] for d in by_date)
    ys = " ".join(str(d["hit_rate"]) for d in by_date)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_report.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/evaluator/report.py apps/python/tests/evaluator/test_report.py
git commit -m "feat(eval): aggregate scores into Mermaid scorecard report"
```

---

### Task 5: CLI エントリポイント

**Files:**
- Create: `apps/python/src/evaluator/__main__.py`
- Create: `apps/python/bin/evaluate.sh`
- Test: `apps/python/tests/evaluator/test_cli.py`

**Interfaces:**
- Consumes: `extract.extract`, `score.score`, `report.build_report`
- Produces: `main(argv: list[str]) -> int` — `argparse` で `extract [target]` / `score [target]` / `report` を振り分け。`target` 省略時は `"all"`。未知サブコマンドは usage を出して `2`。

- [ ] **Step 1: Write the failing test**

```python
# apps/python/tests/evaluator/test_cli.py
from unittest.mock import patch

from src.evaluator.__main__ import main


def test_main_extract_dispatches_target():
    with patch("src.evaluator.__main__.extract.extract") as m:
        assert main(["extract", "2026-06-17"]) == 0
    m.assert_called_once_with("2026-06-17")


def test_main_extract_defaults_to_all():
    with patch("src.evaluator.__main__.extract.extract") as m:
        assert main(["extract"]) == 0
    m.assert_called_once_with("all")


def test_main_report_dispatches():
    with patch("src.evaluator.__main__.report.build_report") as m:
        assert main(["report"]) == 0
    m.assert_called_once_with()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/python && .venv/bin/pytest tests/evaluator/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# apps/python/src/evaluator/__main__.py
from __future__ import annotations

import argparse
import sys

from src.evaluator import extract, report, score


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.evaluator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "score"):
        p = sub.add_parser(name)
        p.add_argument("target", nargs="?", default="all")
    sub.add_parser("report")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.cmd == "extract":
        extract.extract(args.target)
    elif args.cmd == "score":
        score.score(args.target)
    elif args.cmd == "report":
        report.build_report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

```bash
# apps/python/bin/evaluate.sh
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$PROJECT_ROOT/.venv/bin/activate"
PYTHONPATH="$PROJECT_ROOT" exec python -m src.evaluator "$@"
```

- [ ] **Step 4: Make the script executable and run tests**

Run:
```bash
chmod +x apps/python/bin/evaluate.sh
cd apps/python && .venv/bin/pytest tests/evaluator/ -v
```
Expected: PASS (all evaluator tests green)

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/evaluator/__main__.py apps/python/bin/evaluate.sh apps/python/tests/evaluator/test_cli.py
git commit -m "feat(eval): add evaluate CLI entrypoint (extract/score/report)"
```

---

### Task 6: 全体テストと最終確認

**Files:**
- Modify: なし（検証のみ）

- [ ] **Step 1: Run full test suite**

Run: `cd apps/python && .venv/bin/pytest -q`
Expected: 全 pass（既存 + evaluator 新規）

- [ ] **Step 2: Confirm no production briefing path touched**

Run: `git diff --name-only main...HEAD -- apps/python/src/generator/briefing.py apps/python/bin/run.sh`
Expected: 出力なし（既存ブリーフィング経路は不変）

- [ ] **Step 3: Confirm no new dependency added**

Run: `git diff main...HEAD -- apps/python/requirements.in`
Expected: 出力なし

---

## Self-Review

- **Spec coverage:** extract.py(Task2)=抽出 / score.py(Task3)=採点・検証窓・unresolved保留 / report.py(Task4)=集計・Mermaid視覚化 / __main__.py+evaluate.sh(Task5)=CLI / storage.py(Task1)=JSON配置・冪等の土台 / Task6=分離検証。spec 全節をカバー。
- **冪等性:** extract（claims既存スキップ）・score（finalized維持、unresolvedのみ再採点）を Task2/3 で実装・テスト済み。
- **型整合:** claim dict キー（id/theme/direction/targets/horizon_days/type）と score dict キー（id/verdict/confidence/rationale）は全タスクで一貫。`followup_dates` の窓定義（base排他・上端含む）はテストで固定。
- **No placeholders:** 各ステップに実コード・実コマンド・期待出力あり。
