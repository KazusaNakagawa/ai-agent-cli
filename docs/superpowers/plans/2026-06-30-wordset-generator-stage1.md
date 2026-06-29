# Wordset Generator (Stage 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate `english_learn_app`-schema word-set JSON in this repo via `run_claude()` (subscription auth, no API billing), with schema validation and self-numbered UUIDs, replacing the manual "generate elsewhere → copy-paste" flow.

**Architecture:** A pydantic schema module defines the word-set shape. A generator module builds a few-shot prompt, calls `run_claude()`, extracts JSON, validates against the schema, re-generates on validation failure (max 2 retries), self-assigns UUIDs, deduplicates against an existing word set, and writes to `output/`. A thin `bin/` shell wrapper exposes a CLI.

**Tech Stack:** Python 3.13, pydantic 2.13 (already a dependency), `src.claude_runner.run_claude`, pytest.

## Global Constraints

- Code comments and docstrings in **English only** (chat stays Japanese).
- Route all claude CLI calls through `run_claude()` — never `subprocess.run(["claude", ...])`.
- Output files go to `apps/python/output/` (existing convention).
- Target schema (verbatim): `{"words": [{"id", "word", "meaning", "phonetic"(optional), "sentences": [{"id", "english", "japanese", "category"}]}]}`.
- Each word carries **5–6** sentences.
- `id` values are **self-assigned UUIDs** (string form), never taken from the model output.
- `category`: prompt instructs the model to prefer the known set (`一般的な使い方`, `ビジネス`, `日常会話`, `教育`, `テクノロジー`, `人生の教訓`, `健康`, `IT`); validation requires a non-empty string and logs a warning (does NOT reject) when outside the known set.
- All work branches from `dev`.

---

## File Structure

- `apps/python/src/generator/wordset_schema.py` — pydantic models `Sentence`, `Word`, `WordSet`; the `KNOWN_CATEGORIES` constant.
- `apps/python/src/generator/wordset.py` — `generate_wordset()` plus helpers: prompt build, JSON extraction, UUID numbering, dedup, file write.
- `apps/python/prompts/wordset_fewshot.json` — one correct example word (`important`) used as a few-shot exemplar.
- `apps/python/bin/gen_wordset.sh` — CLI wrapper (mirrors `bin/run.sh`).
- `apps/python/tests/generator/test_wordset_schema.py` — schema valid/invalid cases.
- `apps/python/tests/generator/test_wordset.py` — control-flow tests (run_claude mocked), numbering, dedup, merge.

---

### Task 1: Schema module

**Files:**
- Create: `apps/python/src/generator/wordset_schema.py`
- Test: `apps/python/tests/generator/test_wordset_schema.py`

**Interfaces:**
- Produces: `Sentence(BaseModel)` fields `id: str, english: str, japanese: str, category: str`; `Word(BaseModel)` fields `id: str, word: str, meaning: str, phonetic: str | None = None, sentences: list[Sentence]`; `WordSet(BaseModel)` field `words: list[Word]`. Constant `KNOWN_CATEGORIES: frozenset[str]`. `Word` validates `5 <= len(sentences) <= 6`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/python/tests/generator/test_wordset_schema.py
import pytest
from pydantic import ValidationError
from src.generator.wordset_schema import Sentence, Word, WordSet, KNOWN_CATEGORIES


def _sentences(n: int) -> list[dict]:
    return [
        {"id": f"s{i}", "english": "An example sentence.",
         "japanese": "例文。", "category": "一般的な使い方"}
        for i in range(n)
    ]


def test_valid_word_with_five_sentences():
    word = Word(id="w1", word="important", meaning="重要な",
                phonetic="ɪmˈpɔːr.tənt", sentences=_sentences(5))
    assert word.phonetic == "ɪmˈpɔːr.tənt"
    assert len(word.sentences) == 5


def test_phonetic_is_optional():
    word = Word(id="w1", word="x", meaning="y", sentences=_sentences(6))
    assert word.phonetic is None


def test_too_few_sentences_rejected():
    with pytest.raises(ValidationError):
        Word(id="w1", word="x", meaning="y", sentences=_sentences(4))


def test_too_many_sentences_rejected():
    with pytest.raises(ValidationError):
        Word(id="w1", word="x", meaning="y", sentences=_sentences(7))


def test_empty_category_rejected():
    with pytest.raises(ValidationError):
        Sentence(id="s1", english="e", japanese="j", category="")


def test_known_categories_nonempty():
    assert "ビジネス" in KNOWN_CATEGORIES
    assert "一般的な使い方" in KNOWN_CATEGORIES


def test_wordset_round_trips():
    ws = WordSet(words=[Word(id="w1", word="x", meaning="y", sentences=_sentences(5))])
    assert WordSet.model_validate(ws.model_dump()) == ws
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.generator.wordset_schema'`

- [ ] **Step 3: Write the schema module**

```python
# apps/python/src/generator/wordset_schema.py
"""Pydantic models for the english_learn_app word-set JSON schema."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Curated set of common categories. The generator prompt prefers these;
# validation only warns (never rejects) when a category falls outside it,
# because the real corpus has a long tail of 60+ ad-hoc categories.
KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {"一般的な使い方", "ビジネス", "日常会話", "教育",
     "テクノロジー", "人生の教訓", "健康", "IT"}
)


class Sentence(BaseModel):
    id: str
    english: str = Field(min_length=1)
    japanese: str = Field(min_length=1)
    category: str = Field(min_length=1)


class Word(BaseModel):
    id: str
    word: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    phonetic: str | None = None
    sentences: list[Sentence]

    @field_validator("sentences")
    @classmethod
    def _five_or_six(cls, v: list[Sentence]) -> list[Sentence]:
        if not 5 <= len(v) <= 6:
            raise ValueError("each word must have 5 to 6 sentences")
        return v


class WordSet(BaseModel):
    words: list[Word]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset_schema.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/generator/wordset_schema.py apps/python/tests/generator/test_wordset_schema.py
git commit -m "feat: add word-set pydantic schema"
```

---

### Task 2: Few-shot exemplar prompt asset

**Files:**
- Create: `apps/python/prompts/wordset_fewshot.json`
- Test: `apps/python/tests/generator/test_wordset.py` (asset-load test only in this task)

**Interfaces:**
- Produces: a JSON file whose top-level shape matches `WordSet` (one word, `important`, with 5 sentences) — consumed by Task 3's prompt builder.

- [ ] **Step 1: Write the failing test**

```python
# apps/python/tests/generator/test_wordset.py
import json
import pathlib

PROMPTS = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def test_fewshot_asset_matches_schema():
    from src.generator.wordset_schema import WordSet
    data = json.loads((PROMPTS / "wordset_fewshot.json").read_text(encoding="utf-8"))
    ws = WordSet.model_validate(data)
    assert ws.words[0].word == "important"
    assert 5 <= len(ws.words[0].sentences) <= 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset.py::test_fewshot_asset_matches_schema -v`
Expected: FAIL — `FileNotFoundError` for `wordset_fewshot.json`

- [ ] **Step 3: Create the few-shot asset**

```json
{
  "words": [
    {
      "id": "example-id",
      "word": "important",
      "meaning": "重要な",
      "phonetic": "ɪmˈpɔːr.tənt",
      "sentences": [
        {"id": "example-id", "english": "This is an important decision.", "japanese": "これは重要な決断だ。", "category": "一般的な使い方"},
        {"id": "example-id", "english": "Education is important for everyone.", "japanese": "教育は誰にとっても重要だ。", "category": "教育"},
        {"id": "example-id", "english": "It's important to be on time.", "japanese": "時間を守ることは重要だ。", "category": "日常会話"},
        {"id": "example-id", "english": "This document contains important information.", "japanese": "この文書には重要な情報が含まれている。", "category": "ビジネス"},
        {"id": "example-id", "english": "Staying healthy is important.", "japanese": "健康でいることは重要だ。", "category": "健康"}
      ]
    }
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset.py::test_fewshot_asset_matches_schema -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/prompts/wordset_fewshot.json apps/python/tests/generator/test_wordset.py
git commit -m "feat: add word-set few-shot exemplar"
```

---

### Task 3: Generator core — extraction, numbering, dedup, generate

**Files:**
- Create: `apps/python/src/generator/wordset.py`
- Modify: `apps/python/tests/generator/test_wordset.py` (add control-flow tests)

**Interfaces:**
- Consumes: `run_claude(prompt: str, label: str) -> str` from `src.claude_runner`; `WordSet`, `KNOWN_CATEGORIES` from Task 1; `wordset_fewshot.json` from Task 2.
- Produces:
  - `extract_json(text: str) -> dict` — pulls the first balanced `{...}` JSON object out of a raw model response (handles ```` ```json ```` fences); raises `ValueError` if none parses.
  - `assign_ids(ws: WordSet) -> WordSet` — returns a copy with fresh `uuid4()` strings on every word and sentence.
  - `dedup(ws: WordSet, existing_words: set[str]) -> WordSet` — drops words whose lowercased `word` is in `existing_words`.
  - `generate_wordset(words: list[str] | None, theme: str | None, count: int, existing: WordSet | None, max_retries: int = 2) -> WordSet` — orchestrates prompt → `run_claude` → `extract_json` → `WordSet.model_validate` → retry-on-failure → `assign_ids` → `dedup`. Logs a warning per out-of-set category.

- [ ] **Step 1: Write the failing tests**

```python
# append to apps/python/tests/generator/test_wordset.py
from unittest.mock import patch
import pytest


def _raw_response(word="rarity"):
    return (
        "```json\n"
        '{"words":[{"id":"x","word":"%s","meaning":"希少性",'
        '"phonetic":"ˈrer.ə.t̬i","sentences":['
        '{"id":"x","english":"Its rarity makes it valuable.","japanese":"その希少性が価値を生む。","category":"一般的な使い方"},'
        '{"id":"x","english":"Rarity drives demand.","japanese":"希少性が需要を生む。","category":"ビジネス"},'
        '{"id":"x","english":"He studied the rarity of the species.","japanese":"彼はその種の希少性を研究した。","category":"教育"},'
        '{"id":"x","english":"Rarity is common in collectibles.","japanese":"収集品では希少性はよくある。","category":"日常会話"},'
        '{"id":"x","english":"The rarity surprised everyone.","japanese":"その希少性は皆を驚かせた。","category":"一般的な使い方"}'
        "]}]}\n```"
    ) % word


def test_extract_json_handles_fences():
    from src.generator.wordset import extract_json
    data = extract_json(_raw_response())
    assert data["words"][0]["word"] == "rarity"


def test_extract_json_raises_on_garbage():
    from src.generator.wordset import extract_json
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_assign_ids_replaces_all_ids():
    from src.generator.wordset import extract_json, assign_ids
    from src.generator.wordset_schema import WordSet
    ws = assign_ids(WordSet.model_validate(extract_json(_raw_response())))
    word = ws.words[0]
    assert word.id != "x"
    ids = [word.id] + [s.id for s in word.sentences]
    assert len(ids) == len(set(ids))  # all unique


def test_dedup_drops_existing():
    from src.generator.wordset import extract_json, dedup
    from src.generator.wordset_schema import WordSet
    ws = WordSet.model_validate(extract_json(_raw_response()))
    assert dedup(ws, {"rarity"}).words == []
    assert len(dedup(ws, {"other"}).words) == 1


def test_generate_retries_on_invalid_then_succeeds():
    from src.generator import wordset
    bad = "not json"
    good = _raw_response()
    with patch.object(wordset, "run_claude", side_effect=[bad, good]) as m:
        ws = wordset.generate_wordset(words=["rarity"], theme=None, count=1, existing=None)
    assert m.call_count == 2
    assert ws.words[0].word == "rarity"
    assert ws.words[0].id != "x"  # ids reassigned


def test_generate_raises_after_max_retries():
    from src.generator import wordset
    with patch.object(wordset, "run_claude", return_value="garbage"):
        with pytest.raises(ValueError):
            wordset.generate_wordset(words=["rarity"], theme=None, count=1,
                                     existing=None, max_retries=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.generator.wordset'`

- [ ] **Step 3: Write the generator core**

```python
# apps/python/src/generator/wordset.py
"""Generate english_learn_app word-set JSON via the claude CLI."""
from __future__ import annotations

import json
import logging
import pathlib
import uuid

from src.claude_runner import run_claude
from src.generator.wordset_schema import KNOWN_CATEGORIES, WordSet

logger = logging.getLogger(__name__)

PROMPTS_DIR = pathlib.Path(__file__).resolve().parents[1].parent / "prompts"
FEWSHOT_PATH = PROMPTS_DIR / "wordset_fewshot.json"
TIMEOUT = 300


def _load_fewshot() -> str:
    return FEWSHOT_PATH.read_text(encoding="utf-8").strip()


def extract_json(text: str) -> dict:
    """Extract the first balanced JSON object from a raw model response."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON object: {exc}") from exc
    raise ValueError("unbalanced JSON braces in response")


def assign_ids(ws: WordSet) -> WordSet:
    """Return a copy with fresh UUID strings on every word and sentence."""
    return WordSet(
        words=[
            word.model_copy(
                update={
                    "id": str(uuid.uuid4()),
                    "sentences": [
                        s.model_copy(update={"id": str(uuid.uuid4())})
                        for s in word.sentences
                    ],
                }
            )
            for word in ws.words
        ]
    )


def dedup(ws: WordSet, existing_words: set[str]) -> WordSet:
    """Drop words whose lowercased form already exists."""
    lowered = {w.lower() for w in existing_words}
    return WordSet(words=[w for w in ws.words if w.word.lower() not in lowered])


def _build_prompt(words: list[str] | None, theme: str | None, count: int) -> str:
    fewshot = _load_fewshot()
    categories = "、".join(sorted(KNOWN_CATEGORIES))
    if words:
        target = "Generate entries for exactly these words: " + ", ".join(words)
    else:
        target = f"Generate {count} useful English words for the theme: {theme}"
    return (
        "You are generating an English vocabulary word set for a learning app.\n"
        f"{target}\n\n"
        "Rules:\n"
        "- Output ONLY a JSON object, no prose.\n"
        "- Each word needs 5 to 6 example sentences.\n"
        "- Each sentence has english, japanese, and a category.\n"
        f"- Prefer these categories: {categories}.\n"
        "- The id fields can be any placeholder; they will be reassigned.\n\n"
        "Match this exact shape:\n"
        f"{fewshot}\n"
    )


def _warn_unknown_categories(ws: WordSet) -> None:
    for word in ws.words:
        for s in word.sentences:
            if s.category not in KNOWN_CATEGORIES:
                logger.warning("unknown category %r on word %r", s.category, word.word)


def generate_wordset(
    words: list[str] | None,
    theme: str | None,
    count: int,
    existing: WordSet | None,
    max_retries: int = 2,
) -> WordSet:
    """Generate a validated word set, retrying on extraction/validation failure."""
    prompt = _build_prompt(words, theme, count)
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        raw = run_claude(prompt, "wordset generation", timeout=TIMEOUT)
        try:
            ws = WordSet.model_validate(extract_json(raw))
        except (ValueError, Exception) as exc:  # noqa: BLE001 - validation/extract
            last_error = exc
            logger.warning("wordset attempt %d/%d failed: %s", attempt, max_retries, exc)
            prompt = (
                _build_prompt(words, theme, count)
                + f"\n\nYour previous output was invalid: {exc}\nReturn corrected JSON only."
            )
            continue
        _warn_unknown_categories(ws)
        ws = assign_ids(ws)
        if existing is not None:
            ws = dedup(ws, {w.word for w in existing.words})
        return ws
    raise ValueError(f"failed to generate valid word set after {max_retries} attempts: {last_error}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/generator/wordset.py apps/python/tests/generator/test_wordset.py
git commit -m "feat: add word-set generator core"
```

---

### Task 4: CLI entry point + file output / merge

**Files:**
- Modify: `apps/python/src/generator/wordset.py` (add `main()` + file IO)
- Create: `apps/python/bin/gen_wordset.sh`
- Modify: `apps/python/tests/generator/test_wordset.py` (add IO/merge tests)

**Interfaces:**
- Consumes: `generate_wordset(...)`, `WordSet` from Task 3.
- Produces:
  - `load_existing(path: pathlib.Path | None) -> WordSet | None` — loads a word set file, or `None` if path is `None`/missing.
  - `write_output(ws: WordSet, out_dir: pathlib.Path) -> pathlib.Path` — writes `word_set_<unixts>.json` (UTF-8, `ensure_ascii=False`, indent 2), returns the path.
  - `merge_into(existing: WordSet, new: WordSet) -> WordSet` — appends new words after existing.
  - `main(argv: list[str] | None = None) -> int` — argparse CLI: `--words`, `--theme`, `--count` (default 10), `--existing PATH`, `--merge`.

- [ ] **Step 1: Write the failing tests**

```python
# append to apps/python/tests/generator/test_wordset.py
def test_write_output_creates_file(tmp_path):
    from src.generator.wordset import write_output
    from src.generator.wordset_schema import WordSet, Word, Sentence
    ws = WordSet(words=[Word(id="w", word="x", meaning="y", sentences=[
        Sentence(id=f"s{i}", english="e", japanese="j", category="ビジネス") for i in range(5)
    ])])
    out = write_output(ws, tmp_path)
    assert out.exists()
    reloaded = WordSet.model_validate_json(out.read_text(encoding="utf-8"))
    assert reloaded.words[0].word == "x"
    assert "x" in out.read_text(encoding="utf-8")


def test_merge_into_appends(tmp_path):
    from src.generator.wordset import merge_into
    from src.generator.wordset_schema import WordSet, Word, Sentence
    def mk(w):
        return Word(id=w, word=w, meaning="m", sentences=[
            Sentence(id=f"{w}{i}", english="e", japanese="j", category="ビジネス") for i in range(5)
        ])
    merged = merge_into(WordSet(words=[mk("a")]), WordSet(words=[mk("b")]))
    assert [w.word for w in merged.words] == ["a", "b"]


def test_load_existing_none_returns_none():
    from src.generator.wordset import load_existing
    assert load_existing(None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset.py -k "write_output or merge_into or load_existing" -v`
Expected: FAIL — `ImportError: cannot import name 'write_output'`

- [ ] **Step 3: Add file IO + CLI to `wordset.py`**

```python
# append to apps/python/src/generator/wordset.py
import argparse
import time

OUTPUT_DIR = pathlib.Path(__file__).resolve().parents[1].parent / "output"


def load_existing(path: pathlib.Path | None) -> WordSet | None:
    if path is None or not path.exists():
        return None
    return WordSet.model_validate_json(path.read_text(encoding="utf-8"))


def merge_into(existing: WordSet, new: WordSet) -> WordSet:
    return WordSet(words=[*existing.words, *new.words])


def write_output(ws: WordSet, out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"word_set_{int(time.time())}.json"
    out.write_text(
        json.dumps(ws.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate word-set JSON via claude CLI.")
    parser.add_argument("--words", help="comma-separated words")
    parser.add_argument("--theme", help="theme for generated words")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--existing", type=pathlib.Path, help="existing word_set.json for dedup/merge")
    parser.add_argument("--merge", action="store_true", help="merge result into the existing file")
    args = parser.parse_args(argv)

    if not args.words and not args.theme:
        parser.error("provide --words or --theme")

    words = [w.strip() for w in args.words.split(",")] if args.words else None
    existing = load_existing(args.existing)
    result = generate_wordset(words, args.theme, args.count, existing)

    if args.merge and existing is not None:
        result = merge_into(existing, result)

    out = write_output(result, OUTPUT_DIR)
    logger.info("wrote %d words to %s", len(result.words), out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/python && .venv/bin/python -m pytest tests/generator/test_wordset.py -v`
Expected: PASS (all)

- [ ] **Step 5: Create the CLI wrapper**

```bash
# apps/python/bin/gen_wordset.sh
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$PROJECT_ROOT/.venv/bin/activate"
PYTHONPATH="$PROJECT_ROOT" python -m src.generator.wordset "$@"
```

Then: `chmod +x apps/python/bin/gen_wordset.sh`

- [ ] **Step 6: Commit**

```bash
git add apps/python/src/generator/wordset.py apps/python/bin/gen_wordset.sh apps/python/tests/generator/test_wordset.py
git commit -m "feat: add word-set generator CLI and file output"
```

---

### Task 5: Live smoke test (manual, no automated assertion)

**Files:** none (manual verification per `feedback_model_selection_verification`).

- [ ] **Step 1: Run one real generation**

Run: `cd apps/python && bin/gen_wordset.sh --words rarity,experience`
Expected: prints a path under `output/`; the file validates against `WordSet` and ids are UUID-formatted.

- [ ] **Step 2: Verify the output**

Run: `cd apps/python && .venv/bin/python -c "from src.generator.wordset_schema import WordSet; import sys,glob; p=sorted(glob.glob('output/word_set_*.json'))[-1]; ws=WordSet.model_validate_json(open(p).read()); print(p, len(ws.words), [w.word for w in ws.words])"`
Expected: 2 words, `['rarity', 'experience']`, no validation error.

- [ ] **Step 3: Record outcome**

If the live call confirms the mechanism, note success. If the model output shape differs from the few-shot, capture the gap with `judge note` and adjust `_build_prompt` / `extract_json` before proceeding to Stage 2.

---

## Self-Review Notes

- **Spec coverage:** schema (Task 1), few-shot (Task 2), generation+validation+retry+UUID+dedup (Task 3), output+merge+CLI (Task 4), live verification (Task 5). All Stage 1 spec sections covered.
- **Category handling:** spec said "enum constraint"; refined to known-set-preference + warn-not-reject due to the 60+ category long tail in real data. Recorded in Global Constraints.
- **Type consistency:** `generate_wordset`, `extract_json`, `assign_ids`, `dedup`, `write_output`, `merge_into`, `load_existing`, `main` signatures match between definition and tests.
