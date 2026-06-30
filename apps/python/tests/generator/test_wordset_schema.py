import pytest
from pydantic import ValidationError
from src.generator.wordset_schema import Sentence, Word, WordSet, KNOWN_CATEGORIES


def _sentences(n: int) -> list[dict]:
    return [
        {"id": f"s{i}", "english": "An example sentence.",
         "japanese": "例文。", "category": "一般的な使い方"}
        for i in range(n)
    ]


def test_valid_word_with_fifteen_sentences():
    word = Word(id="w1", word="important", meaning="重要な",
                phonetic="ɪmˈpɔːr.tənt", sentences=_sentences(15))
    assert word.phonetic == "ɪmˈpɔːr.tənt"
    assert len(word.sentences) == 15


def test_phonetic_is_optional():
    word = Word(id="w1", word="x", meaning="y", sentences=_sentences(20))
    assert word.phonetic is None


def test_too_few_sentences_rejected():
    with pytest.raises(ValidationError):
        Word(id="w1", word="x", meaning="y", sentences=_sentences(14))


def test_too_many_sentences_rejected():
    with pytest.raises(ValidationError):
        Word(id="w1", word="x", meaning="y", sentences=_sentences(21))


def test_empty_category_rejected():
    with pytest.raises(ValidationError):
        Sentence(id="s1", english="e", japanese="j", category="")


def test_known_categories_nonempty():
    assert "ビジネス" in KNOWN_CATEGORIES
    assert "一般的な使い方" in KNOWN_CATEGORIES


def test_wordset_round_trips():
    ws = WordSet(words=[Word(id="w1", word="x", meaning="y", sentences=_sentences(15))])
    assert WordSet.model_validate(ws.model_dump()) == ws
