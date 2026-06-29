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
        "- Each word needs 15 to 20 example sentences.\n"
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
