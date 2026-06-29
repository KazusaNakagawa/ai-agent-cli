import json
import pathlib

PROMPTS = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def test_fewshot_asset_matches_schema():
    from src.generator.wordset_schema import WordSet
    data = json.loads((PROMPTS / "wordset_fewshot.json").read_text(encoding="utf-8"))
    ws = WordSet.model_validate(data)
    assert ws.words[0].word == "important"
    assert 15 <= len(ws.words[0].sentences) <= 20
