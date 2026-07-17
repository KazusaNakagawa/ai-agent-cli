"""Index and retrieve past daily briefings for cross-date chat RAG (#395).

Reuses the repo-code Indexer/Retriever unchanged: pointing
``LocalLLMConfig.repo_root`` at the briefing output directory and querying a
dedicated Chroma collection (``BRIEFING_COLLECTION_NAME``) is enough — the
extension allowlist already accepts ``.md`` and rejects the extension-less
session-id files under ``output/briefing/.sessions/``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from src.constants import BRIEFING_OUTPUT_DIR

from .clients import ensure_models_available, make_chroma_collection, make_ollama_client
from .config import BRIEFING_COLLECTION_NAME, LocalLLMConfig
from .indexer import Indexer, IndexStats
from .retriever import RetrievedChunk, Retriever


def _briefing_cfg(cfg: LocalLLMConfig, briefing_dir: Path | None) -> LocalLLMConfig:
    return dataclasses.replace(cfg, repo_root=briefing_dir or BRIEFING_OUTPUT_DIR)


def index_briefings(cfg: LocalLLMConfig, *, briefing_dir: Path | None = None) -> IndexStats:
    """Incrementally index ``output/briefing/*.md`` into the briefings collection."""
    bcfg = _briefing_cfg(cfg, briefing_dir)
    olm = make_ollama_client(bcfg)
    coll = make_chroma_collection(bcfg, collection_name=BRIEFING_COLLECTION_NAME)
    return Indexer(bcfg, collection=coll, ollama_client=olm).run()


def retrieve_briefing_context(
    cfg: LocalLLMConfig,
    question: str,
    *,
    top_k: int | None = None,
    briefing_dir: Path | None = None,
) -> list[RetrievedChunk]:
    """Top-k retrieval over indexed past briefings for ``question``.

    Raises ``OllamaUnavailable`` up front (via ``ensure_models_available``) if
    ``embed_model`` isn't pulled, instead of letting a raw
    ``ollama.ResponseError`` ("model not found") surface from the embeddings
    call — the web router maps ``OllamaUnavailable`` to a clean 503.
    """
    bcfg = _briefing_cfg(cfg, briefing_dir)
    olm = make_ollama_client(bcfg)
    ensure_models_available(olm, bcfg.embed_model, embed_model=None)
    coll = make_chroma_collection(bcfg, collection_name=BRIEFING_COLLECTION_NAME)
    return Retriever(bcfg, collection=coll, ollama_client=olm).retrieve(question, top_k=top_k)
