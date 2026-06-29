import json
import pathlib
from unittest.mock import patch
import pytest

PROMPTS = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def test_fewshot_asset_matches_schema():
    from src.generator.wordset_schema import WordSet
    data = json.loads((PROMPTS / "wordset_fewshot.json").read_text(encoding="utf-8"))
    ws = WordSet.model_validate(data)
    assert ws.words[0].word == "important"
    assert 15 <= len(ws.words[0].sentences) <= 20


def _raw_response(word="rarity", n_sentences=16):
    """Build a fenced JSON response with n_sentences (default 16, inside 15-20)."""
    obj = {
        "words": [
            {
                "id": "x",
                "word": word,
                "meaning": "希少性",
                "phonetic": "ˈrer.ə.t̬i",
                "sentences": [
                    {
                        "id": "x",
                        "english": f"Its rarity makes example {i} valuable.",
                        "japanese": f"その希少性が例{i}の価値を生む。",
                        "category": "一般的な使い方",
                    }
                    for i in range(n_sentences)
                ],
            }
        ]
    }
    return "```json\n" + json.dumps(obj, ensure_ascii=False) + "\n```"


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


def test_generate_raises_without_words_or_theme():
    from src.generator import wordset
    with pytest.raises(ValueError, match="provide words or theme"):
        wordset.generate_wordset(None, None, 1, None)


def test_generate_raises_after_max_retries():
    from src.generator import wordset
    with patch.object(wordset, "run_claude", return_value="garbage"):
        with pytest.raises(ValueError):
            wordset.generate_wordset(words=["rarity"], theme=None, count=1,
                                     existing=None, max_retries=2)
