"""Top-k retrieval from Chroma and generation with Ollama."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol

from .config import LocalLLMConfig

PROMPT_TEMPLATE = """以下のコード断片だけを根拠に、日本語で質問に答えてください。
断片に書かれていないことは推測せず「分からない」と答えてください。
回答の末尾に Sources: として参照ファイル名を列挙してください。

## Context
{context}

## Question
{question}
"""


@dataclass(frozen=True)
class RetrievedChunk:
    source_path: str
    start_line: int
    end_line: int
    text: str
    distance: float


class _CollectionLike(Protocol):
    def query(self, query_embeddings, n_results) -> dict: ...


class _OllamaLike(Protocol):
    def embeddings(self, model: str, prompt: str) -> dict: ...
    def generate(self, model: str, prompt: str, stream: bool) -> Iterable[dict]: ...


def build_context_text(chunks: Iterable[RetrievedChunk]) -> str:
    parts: list[str] = []
    for c in chunks:
        parts.append(f"[{c.source_path}:{c.start_line}-{c.end_line}]\n{c.text}")
    return "\n---\n".join(parts)


class Retriever:
    def __init__(
        self,
        cfg: LocalLLMConfig,
        *,
        collection: _CollectionLike,
        ollama_client: _OllamaLike,
    ) -> None:
        self.cfg = cfg
        self.collection = collection
        self.ollama = ollama_client

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self.cfg.top_k
        qv = self.ollama.embeddings(model=self.cfg.embed_model, prompt=question)["embedding"]
        res = self.collection.query(query_embeddings=[qv], n_results=k)
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        return [
            RetrievedChunk(
                source_path=m["source_path"],
                start_line=int(m["start_line"]),
                end_line=int(m["end_line"]),
                text=d,
                distance=float(dist),
            )
            for d, m, dist in zip(docs, metas, dists, strict=True)
        ]

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> Iterator[str]:
        prompt = PROMPT_TEMPLATE.format(
            context=build_context_text(chunks),
            question=question,
        )
        for piece in self.ollama.generate(
            model=self.cfg.model, prompt=prompt, stream=True
        ):
            tok = piece.get("response", "")
            if tok:
                yield tok
            if piece.get("done"):
                break
