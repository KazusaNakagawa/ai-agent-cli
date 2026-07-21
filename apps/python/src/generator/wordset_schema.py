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
    def _fifteen_to_twenty(cls, v: list[Sentence]) -> list[Sentence]:
        if not 15 <= len(v) <= 20:
            raise ValueError("each word must have 15 to 20 sentences")
        return v


class WordSet(BaseModel):
    words: list[Word]
