# Local-LLM Briefing Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Issue #142 — Add `bin/local_llm.sh --briefing [--notion]` that produces a daily briefing via Ollama (qwen2.5:7b) using the existing `BriefingConfig`, saves it to `apps/python/output/briefing/local_<YYYY-MM-DD>.md`, and optionally posts to Notion. Run alongside the Claude path without touching it.

**Architecture:** Three thin pure-function units in `local_llm/briefing.py` (`build_local_briefing_prompt` / `generate_local_briefing` / `compose_briefing_md`) plus one new CLI command `_cmd_briefing` that wires `fetch_stock_moves` + Ollama + `notifier.notion.send_to_notion`. The prompt template is a new file `prompts/local_briefing.md` so the Claude prompt is untouched.

**Tech Stack:** Python 3.12 / Ollama Python client / argparse / existing `generator.briefing._build_*_context()` helpers / `notifier.notion.send_to_notion`

**Spec:** `docs/superpowers/specs/2026-06-08-local-briefing-design.md`

**Branch:** `feature/issue-142-local-briefing` (already exists, spec committed)

---

## File Structure

| Path | Responsibility | New / Mod |
|---|---|---|
| `apps/python/prompts/local_briefing.md` | Prompt template (no WebSearch instruction; `$themes` `$tickers` `$geopolitical` `$watch_events` `$stocks` placeholders) | NEW |
| `apps/python/src/local_llm/briefing.py` | `build_local_briefing_prompt(cfg, stocks)` / `generate_local_briefing(prompt, ollama, model)` / `compose_briefing_md(body, *, model, generated_at)` | NEW |
| `apps/python/src/local_llm/cli.py` | Add `--briefing` + `--notion` flags, `_cmd_briefing(cfg, *, post_to_notion)` | MOD |
| `apps/python/tests/local_llm/test_briefing.py` | 5 unit tests covering prompt build, caveat header, stream collection, file save, Notion fanout | NEW |
| `README.md` | Append `--briefing` line to the Local LLM section | MOD |

---

## Task 1: Prompt template

**Files:**
- Create: `apps/python/prompts/local_briefing.md`

- [ ] **Step 1: Inspect the existing prompt**

```bash
cat apps/python/prompts/briefing.md
```

You will copy this and remove the WebSearch instruction.

- [ ] **Step 2: Create `apps/python/prompts/local_briefing.md`**

Write this file verbatim:

````markdown
あなたは私専用の世界情勢アナリストです。
下記の入力データと、あなたが既に知っている範囲の知識だけを根拠に、「My World Briefing（ローカル版）」を日本語で作成してください。
**確認できない最新情報は推測しないでください。** 不明な点は「情報なし」と書いてください。

## 入力情報
- 関心テーマ: $themes
- 保有・注目銘柄: $tickers

## 地政学リスクと市場への因果関係
$geopolitical

## 監視イベント（IPO・規制・重要発表）
$watch_events

## 株価（前日比）
$stocks

## 出力フォーマット

下記の構造を **そのまま** 使用してください。
- 大セクションは `###`、サブセクションは `####` を使用
- `####` の後ろに別の `#` を付けないこと（例: `### ####` は誤り）
- 箇条書きは `-` を使用

---

### 今日のサマリー（1文）

〜入力データから読み取れる範囲で1文〜

---

### なぜ動いたか（ストーリー）

#### トピック1（← 該当する地政学リスクや監視イベントの名称）
〜地政学・感情・需給の観点から、入力データに基づき〜

#### トピック2
〜内容〜

---

### 地政学と株式の因果関係

上記の地政学リスクが過去・現在の市場にどう影響したかを関連銘柄・セクターと紐づけてテーブルで説明。

---

### 自分への示唆

#### PLTR（← 銘柄ごとに分けて記述）
保有者として意識すべきことを1〜2行で

#### NVDA
保有者として意識すべきことを1〜2行で

---

### 参考記事

（モデル知識ベースなので URL は省略可。代わりに「過去に話題になったテーマ」を箇条書きで）

---

簡潔にまとめてください。
````

- [ ] **Step 3: Commit**

```bash
git add apps/python/prompts/local_briefing.md
git commit -m "feat(local-llm): add briefing prompt template without WebSearch"
```

---

## Task 2: `build_local_briefing_prompt` (pure function)

**Files:**
- Create: `apps/python/src/local_llm/briefing.py`
- Create: `apps/python/tests/local_llm/test_briefing.py`

- [ ] **Step 1: Write the failing test**

`apps/python/tests/local_llm/test_briefing.py`:

```python
from datetime import datetime

import pytest

from src.config import BriefingConfig, GeopoliticalConfig, PortfolioConfig, WatchSector
from src.local_llm.briefing import (
    build_local_briefing_prompt,
    compose_briefing_md,
    generate_local_briefing,
)


def _minimal_cfg() -> BriefingConfig:
    # watch_sectors requires min_length=1; portfolio.tickers requires min_length=1
    return BriefingConfig(
        portfolio=PortfolioConfig(tickers=["PLTR", "NVDA"], themes=["AI", "半導体"]),
        watch_sectors=[WatchSector(sector="AI & Cloud", tickers=["NVDA"])],
        geopolitical=GeopoliticalConfig(),
        watch_events=[],
        discord_token="",
        discord_channel_id="",
        notion_api_key="",
        notion_database_id="",
    )


def test_build_local_briefing_prompt_inserts_inputs():
    cfg = _minimal_cfg()
    out = build_local_briefing_prompt(cfg, stocks="PLTR +2.1%\nNVDA +0.5%")

    assert "AI" in out
    assert "半導体" in out
    assert "PLTR" in out
    assert "NVDA" in out
    assert "PLTR +2.1%" in out
    assert "WebSearch" not in out  # local prompt removes the WebSearch instruction
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py::test_build_local_briefing_prompt_inserts_inputs -v
```

Expected: `ImportError: cannot import name 'build_local_briefing_prompt'`.

- [ ] **Step 3: Implement**

`apps/python/src/local_llm/briefing.py`:

```python
"""ローカル LLM 用ブリーフィング生成。プロンプト組立・Ollama 呼び出し・MD 組成。"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Iterator, Protocol

from src.config import BriefingConfig
from src.generator.briefing import (
    _build_geopolitical_context,
    _build_watch_events_context,
    _join_safe,
)
from src.generator.prompt import render


def build_local_briefing_prompt(cfg: BriefingConfig, stocks: str) -> str:
    """既存ヘルパを再利用して local_briefing.md テンプレートに入力を流し込む。"""
    tickers = _join_safe(cfg.portfolio.tickers, sep=", ")
    themes = _join_safe(cfg.portfolio.themes, sep=", ")
    return render(
        "local_briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=_build_geopolitical_context(cfg),
        watch_events=_build_watch_events_context(cfg),
        stocks=stocks,
    )
```

- [ ] **Step 4: Run test (expect PASS)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py::test_build_local_briefing_prompt_inserts_inputs -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/briefing.py apps/python/tests/local_llm/test_briefing.py
git commit -m "feat(local-llm): add build_local_briefing_prompt"
```

---

## Task 3: `generate_local_briefing` (Ollama stream collector)

**Files:**
- Modify: `apps/python/src/local_llm/briefing.py`
- Modify: `apps/python/tests/local_llm/test_briefing.py`

- [ ] **Step 1: Add the failing test**

Append to `apps/python/tests/local_llm/test_briefing.py`:

```python
class FakeOllama:
    def __init__(self, tokens, captured=None):
        self._tokens = tokens
        self._captured = captured if captured is not None else {}

    def generate(self, model, prompt, stream):
        assert stream is True
        self._captured["model"] = model
        self._captured["prompt"] = prompt
        for t in self._tokens:
            yield {"response": t, "done": False}
        yield {"response": "", "done": True}


def test_generate_local_briefing_collects_stream(capsys):
    captured: dict = {}
    olm = FakeOllama(tokens=["Hel", "lo ", "世界"], captured=captured)

    full = generate_local_briefing("PROMPT", ollama_client=olm, model="qwen2.5:7b")

    assert full == "Hello 世界"
    assert captured["model"] == "qwen2.5:7b"
    assert captured["prompt"] == "PROMPT"
    # also streams to stdout for the user
    assert "Hello 世界" in capsys.readouterr().out
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py::test_generate_local_briefing_collects_stream -v
```

Expected: `ImportError` for `generate_local_briefing`.

- [ ] **Step 3: Implement**

Append to `apps/python/src/local_llm/briefing.py`:

```python
import sys


class _OllamaLike(Protocol):
    def generate(self, model: str, prompt: str, stream: bool) -> Iterable[dict]: ...


def generate_local_briefing(
    prompt: str,
    *,
    ollama_client: _OllamaLike,
    model: str,
) -> str:
    """Ollama の stream を 1 本のテキストに集約しつつ stdout にもエコーする。"""
    pieces: list[str] = []
    for piece in ollama_client.generate(model=model, prompt=prompt, stream=True):
        tok = piece.get("response", "")
        if tok:
            pieces.append(tok)
            print(tok, end="", flush=True)
        if piece.get("done"):
            break
    print()  # final newline so the next CLI output starts fresh
    return "".join(pieces)
```

- [ ] **Step 4: Run test (expect PASS)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py::test_generate_local_briefing_collects_stream -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/briefing.py apps/python/tests/local_llm/test_briefing.py
git commit -m "feat(local-llm): add generate_local_briefing stream collector"
```

---

## Task 4: `compose_briefing_md` (caveat header + body)

**Files:**
- Modify: `apps/python/src/local_llm/briefing.py`
- Modify: `apps/python/tests/local_llm/test_briefing.py`

- [ ] **Step 1: Add the failing test**

Append to `apps/python/tests/local_llm/test_briefing.py`:

```python
def test_compose_briefing_md_emits_caveat_then_body():
    md = compose_briefing_md(
        body="### 今日のサマリー\n本文\n",
        model="qwen2.5:7b",
        generated_at=datetime(2026, 6, 8, 9, 15, 0),
    )

    head, _, body = md.partition("\n\n---\n\n")
    assert "ローカル LLM" in head
    assert "qwen2.5:7b" in head
    assert "WebSearch 未使用" in head
    assert "2026-06-08T09:15:00" in head
    assert body.startswith("### 今日のサマリー")
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py::test_compose_briefing_md_emits_caveat_then_body -v
```

Expected: `ImportError` or `NameError` for `compose_briefing_md`.

- [ ] **Step 3: Implement**

Append to `apps/python/src/local_llm/briefing.py`:

```python
def compose_briefing_md(
    body: str,
    *,
    model: str,
    generated_at: datetime,
) -> str:
    """Caveat ヘッダと本文を `---` で連結する。"""
    head = (
        "> **※ ローカル LLM 生成（実験版）**\n"
        f"> - model: {model}\n"
        "> - WebSearch 未使用 — モデルの学習知識と入力データのみで生成\n"
        f"> - generated_at: {generated_at.isoformat(timespec='seconds')}\n"
    )
    return f"{head}\n---\n\n{body.rstrip()}\n"
```

- [ ] **Step 4: Run test (expect PASS)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py::test_compose_briefing_md_emits_caveat_then_body -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/briefing.py apps/python/tests/local_llm/test_briefing.py
git commit -m "feat(local-llm): add compose_briefing_md with caveat header"
```

---

## Task 5: CLI wiring — `--briefing` and `--notion`

**Files:**
- Modify: `apps/python/src/local_llm/cli.py`
- Modify: `apps/python/tests/local_llm/test_briefing.py`

- [ ] **Step 1: Add the failing tests**

Append to `apps/python/tests/local_llm/test_briefing.py`:

```python
from pathlib import Path

from src.local_llm import cli


class _FakeRunCLI:
    """Helper for cli._cmd_briefing tests: monkeypatches the four collaborators."""

    def __init__(self, monkeypatch, tmp_path, *, briefing_text="### 今日\nbody\n"):
        self.notion_calls: list[dict] = []
        self.output_dir = tmp_path / "out"
        self.output_dir.mkdir()

        monkeypatch.setattr(cli, "BRIEFING_OUTPUT_DIR", self.output_dir)
        monkeypatch.setattr(cli, "fetch_stock_moves", lambda tickers: "PLTR +1%")
        monkeypatch.setattr(
            cli, "load_briefing_config", lambda: _minimal_cfg()
        )
        monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
        monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
        monkeypatch.setattr(
            cli,
            "build_local_briefing_prompt",
            lambda cfg, stocks: "PROMPT",
        )
        monkeypatch.setattr(
            cli,
            "generate_local_briefing",
            lambda prompt, *, ollama_client, model: briefing_text,
        )

        def _fake_notion(text, api_key, db_id, *, title, tags=None, extra_properties=None):
            self.notion_calls.append({"text": text, "title": title, "tags": tags})
            return "https://www.notion.so/fake"

        monkeypatch.setattr(cli, "send_to_notion", _fake_notion)


def test_cmd_briefing_writes_local_file_and_skips_notion(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    files = list(fake.output_dir.glob("local_*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "ローカル LLM" in content
    assert "### 今日" in content
    assert fake.notion_calls == []


def _cfg_with_notion() -> BriefingConfig:
    return _minimal_cfg().model_copy(update={
        "notion_api_key": "k",
        "notion_database_id": "d",
    })


def test_cmd_briefing_posts_to_notion_when_flag(monkeypatch, tmp_path):
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "load_briefing_config", _cfg_with_notion)

    rc = cli.main(["--briefing", "--notion", "--root", str(tmp_path)])

    assert rc == 0
    assert len(fake.notion_calls) == 1
    call = fake.notion_calls[0]
    assert "ローカルブリーフィング" in call["title"]
    assert "local" in (call["tags"] or [])
    assert "agent" in (call["tags"] or [])


def test_cmd_briefing_notion_without_flag_is_noop(monkeypatch, tmp_path):
    """--notion 未指定なら NOTION_API_KEY が揃っていても投稿しない。"""
    fake = _FakeRunCLI(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "load_briefing_config", _cfg_with_notion)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    assert fake.notion_calls == []
```

- [ ] **Step 2: Run tests (expect FAIL)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_briefing.py -v -k briefing
```

Expected: 3 new tests FAIL (missing `--briefing` flag and `_cmd_briefing`).

- [ ] **Step 3: Modify the argparse group in `apps/python/src/local_llm/cli.py`**

Find `_build_parser()` and add `--briefing` and `--notion`. Replace the function:

```python
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m local_llm")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", action="store_true", help="リポジトリを index")
    group.add_argument("--ask", metavar="QUESTION", help="質問に回答（生成あり）")
    group.add_argument("--sources", metavar="QUESTION", help="top-k のファイル位置だけ表示")
    group.add_argument("--status", action="store_true", help="現在の index 統計を表示")
    group.add_argument("--briefing", action="store_true", help="ローカル LLM で日次ブリーフィングを生成")
    p.add_argument("--root", type=Path, default=None, help="リポジトリルート override")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--model", default=None, help="生成モデル override")
    p.add_argument("--reset", action="store_true", help="--index 時に .chroma_db を消して全件再構築")
    p.add_argument("--notion", action="store_true", help="--briefing 時に Notion へも投稿する")
    return p
```

- [ ] **Step 4: Add imports at the top of `cli.py`**

After the existing imports, append:

```python
from src.config import load_config as load_briefing_config
from src.constants import BRIEFING_OUTPUT_DIR
from src.fetcher.stocks import fetch_stock_moves
from src.notifier.notion import send_to_notion

from .briefing import (
    build_local_briefing_prompt,
    compose_briefing_md,
    generate_local_briefing,
)
```

Note: `from src.config import load_config` would shadow `local_llm.config.load_config`. Alias to `load_briefing_config` to keep them distinct in this file.

- [ ] **Step 5: Add `--briefing` dispatch to `main()`**

In `cli.main()`, after the existing dispatch block, add the `--briefing` branch. Replace the dispatch tail:

```python
    if args.status:
        return _cmd_status(cfg)
    if args.index:
        return _cmd_index(cfg, reset=args.reset)
    if args.sources is not None:
        return _cmd_sources(cfg, args.sources)
    if args.ask is not None:
        return _cmd_ask(cfg, args.ask)
    if args.briefing:
        return _cmd_briefing(cfg, post_to_notion=args.notion)
    return 2
```

- [ ] **Step 6: Add `_cmd_briefing` to `cli.py`**

Append at the end of `cli.py`:

```python
def _cmd_briefing(cfg, *, post_to_notion: bool) -> int:
    from datetime import datetime, date

    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    briefing_cfg = load_briefing_config()
    stocks = fetch_stock_moves(briefing_cfg.portfolio.tickers)

    prompt = build_local_briefing_prompt(briefing_cfg, stocks)
    body = generate_local_briefing(prompt, ollama_client=olm, model=cfg.model)
    md = compose_briefing_md(body, model=cfg.model, generated_at=datetime.now())

    BRIEFING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    out_path = BRIEFING_OUTPUT_DIR / f"local_{today}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\nsaved {out_path}", file=sys.stderr)

    if post_to_notion:
        if not (briefing_cfg.notion_api_key and briefing_cfg.notion_database_id):
            print(
                "Error: --notion specified but NOTION_API_KEY / NOTION_DATABASE_ID not set",
                file=sys.stderr,
            )
            return 1
        url = send_to_notion(
            md,
            briefing_cfg.notion_api_key,
            briefing_cfg.notion_database_id,
            title=f"ローカルブリーフィング — {today}",
            tags=["agent", "local"],
        )
        if url:
            print(f"notion: {url}", file=sys.stderr)
        else:
            print("Notion 投稿に失敗しました", file=sys.stderr)

    return 0
```

- [ ] **Step 7: Run tests (expect PASS)**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/ -v
```

Expected: all `tests/local_llm/` tests pass (20 from #140 + 6 new = 26).

- [ ] **Step 8: Commit**

```bash
git add apps/python/src/local_llm/cli.py apps/python/tests/local_llm/test_briefing.py
git commit -m "feat(local-llm): add --briefing CLI with optional --notion"
```

---

## Task 6: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find the current usage block**

```bash
grep -n "bin/local_llm.sh" README.md
```

You should find a block starting with `bin/local_llm.sh --index`.

- [ ] **Step 2: Add the briefing line**

In `README.md`, find:

```markdown
bin/local_llm.sh --ask "認証はどう動く？"
bin/local_llm.sh --sources "認証はどう動く？"  # retrieval-only debug
bin/local_llm.sh --index --reset               # rebuild from scratch
```

Replace with:

```markdown
bin/local_llm.sh --ask "認証はどう動く？"
bin/local_llm.sh --sources "認証はどう動く？"  # retrieval-only debug
bin/local_llm.sh --index --reset               # rebuild from scratch
bin/local_llm.sh --briefing                    # generate daily briefing locally (saves local_<date>.md)
bin/local_llm.sh --briefing --notion           # ...and post to Notion alongside the Claude version
```

Then immediately below the existing override-env paragraph, add:

```markdown
The `--briefing` path is experimental and does **not** use WebSearch — output is grounded only in the structured `briefing.json` input and the model's training knowledge. Tracked under [#142](https://github.com/KazusaNakagawa/ai-agent-cli/issues/142).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(local-llm): document --briefing and --notion flags"
```

---

## Task 7: 実機検証 + PR

Real-Ollama smoke run that the unit tests cannot cover. Requires `ollama serve`, `qwen2.5:7b`, `briefing.json` configured.

- [ ] **Step 1: Run the local briefing**

```bash
bin/local_llm.sh --briefing
```

Expected: tokens stream to stdout, ends with `saved apps/python/output/briefing/local_<today>.md`.

- [ ] **Step 2: Verify the saved markdown**

```bash
head -10 apps/python/output/briefing/local_$(date +%Y-%m-%d).md
```

Expected:
- First line is `> **※ ローカル LLM 生成（実験版）**`
- Caveat header includes `model: qwen2.5:7b` and `WebSearch 未使用`
- Followed by `---` separator and the generated body starting with `### 今日のサマリー（1文）`

- [ ] **Step 3: Locate the same day's Claude briefing for the PR comparison**

```bash
ls apps/python/output/briefing/briefing_$(date +%Y-%m-%d).md 2>/dev/null \
  || ls apps/python/output/briefing/briefing_*.md | tail -1
```

If a same-day Claude briefing exists, use it. Otherwise use the latest one and note the date in the PR.

- [ ] **Step 4: Test Notion fanout (manual)**

Only run this after confirming `NOTION_API_KEY` and `NOTION_DATABASE_ID` are set:

```bash
bin/local_llm.sh --briefing --notion
```

Expected: stderr ends with `notion: https://www.notion.so/...`. Open the URL and confirm a new page tagged `agent, local` was created.

- [ ] **Step 5: Confirm the Claude path is untouched**

```bash
bin/run.sh  # or whatever the operator normally runs — DO NOT run if it would spam Notion in prod
# instead, do a dry-run:
.venv/bin/python bin/briefing.py --dry-run
```

Expected: dry-run succeeds and no changes to the Claude path's behavior.

- [ ] **Step 6: Push and open PR**

```bash
git push -u origin feature/issue-142-local-briefing
gh pr create --base dev --title "feat(local-llm): add --briefing path with Notion delivery (#142)" --body "$(cat <<'EOF'
## Summary
- New `bin/local_llm.sh --briefing` produces a daily briefing via Ollama (default `qwen2.5:7b`) using the same `BriefingConfig` as the Claude path
- `--notion` flag posts the markdown to Notion via the existing `notifier.notion.send_to_notion`, tagged `agent, local`
- The Claude briefing / its schedule / its Notion entries are untouched
- WebSearch is intentionally NOT used — output is grounded in `briefing.json` and the model's training knowledge only; a caveat header makes this explicit

## Quality comparison (same day)

### Claude version (excerpt)
<paste first 15 lines of briefing_<date>.md>

### Local version (excerpt)
<paste first 15 lines of local_<date>.md>

## Spec / Plan
- Spec: `docs/superpowers/specs/2026-06-08-local-briefing-design.md`
- Plan: `docs/superpowers/plans/2026-06-08-local-briefing.md`

## Test plan
- [x] `pytest tests/local_llm/` — all PASS (20 from #140 + 6 new)
- [x] `bin/local_llm.sh --briefing` writes `local_<date>.md` with caveat header
- [x] Same MD posts to Notion when `--notion` is set (verified with a real page)
- [x] Existing `bin/briefing.py --dry-run` still works
- [ ] Reviewer reads the caveat header and confirms WebSearch is not used

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Replace the `<paste ...>` placeholders with actual file excerpts before running.

---

## Self-review notes

- Spec coverage: T1 prompt, T2 prompt-builder, T3 generator, T4 composer, T5 CLI+Notion fanout, T6 README, T7 verification. All spec sections (architecture / data flow / CLI / error handling / tests / acceptance) map.
- Naming consistency: `build_local_briefing_prompt`, `generate_local_briefing`, `compose_briefing_md`, `_cmd_briefing`, `load_briefing_config` (aliased to avoid clash with `local_llm.config.load_config`). All references in later tasks match earlier definitions.
- The test in T5 patches `cli.load_briefing_config` etc. by name — the names are introduced as imports in Step 4 of T5 so the monkeypatch targets exist.
- BriefingConfig field names referenced in tests (`portfolio.tickers`, `notion_api_key`, `notion_database_id`) are from `src.config.BriefingConfig`. If the schema differs the implementer must inspect and adapt — see `apps/python/src/config.py`.
- No placeholders. All code blocks are complete.
