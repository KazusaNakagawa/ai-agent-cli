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


def test_generate_logs_raw_response_on_terminal_failure(caplog):
    """On exhausting all retries, the raw model response must be logged at ERROR."""
    import logging
    from src.generator import wordset

    garbage = "THIS_IS_GARBAGE_RAW_RESPONSE"
    with patch.object(wordset, "run_claude", return_value=garbage):
        with caplog.at_level(logging.ERROR, logger="src.generator.wordset"):
            with pytest.raises(ValueError):
                wordset.generate_wordset(words=["rarity"], theme=None, count=1,
                                         existing=None, max_retries=2)
    assert garbage in caplog.text


def test_write_output_creates_file(tmp_path):
    from src.generator.wordset import write_output
    from src.generator.wordset_schema import WordSet, Word, Sentence
    ws = WordSet(words=[Word(id="w", word="x", meaning="y", sentences=[
        Sentence(id=f"s{i}", english="e", japanese="j", category="ビジネス") for i in range(15)
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
            Sentence(id=f"{w}{i}", english="e", japanese="j", category="ビジネス") for i in range(15)
        ])
    merged = merge_into(WordSet(words=[mk("a")]), WordSet(words=[mk("b")]))
    assert [w.word for w in merged.words] == ["a", "b"]


def test_load_existing_none_returns_none():
    from src.generator.wordset import load_existing
    assert load_existing(None) is None
