"""Index and retrieve Obsidian vault notes for chat RAG.

Same pattern as ``briefing_index``: point ``LocalLLMConfig.repo_root`` at the
vault directory and use a dedicated Chroma collection. The vault's internal
folders (``.obsidian/``, templates, trash) are excluded via
``LocalLLMConfig.extra_exclude_dirs`` so they never get indexed.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from .clients import ensure_models_available, make_chroma_collection, make_ollama_client
from .config import OBSIDIAN_COLLECTION_NAME, LocalLLMConfig
from .indexer import Indexer, IndexStats
from .retriever import RetrievedChunk, Retriever


def _vault_cfg(cfg: LocalLLMConfig, vault_path: Path, exclude_dirs: list[str]) -> LocalLLMConfig:
    return dataclasses.replace(
        cfg, repo_root=vault_path, extra_exclude_dirs=frozenset(exclude_dirs)
    )


def index_obsidian(
    cfg: LocalLLMConfig, *, vault_path: Path, exclude_dirs: list[str]
) -> IndexStats:
    """Incrementally index vault Markdown into the obsidian collection."""
    vcfg = _vault_cfg(cfg, vault_path, exclude_dirs)
    olm = make_ollama_client(vcfg)
    coll = make_chroma_collection(vcfg, collection_name=OBSIDIAN_COLLECTION_NAME)
    return Indexer(vcfg, collection=coll, ollama_client=olm).run()


def retrieve_obsidian_context(
    cfg: LocalLLMConfig,
    question: str,
    *,
    top_k: int | None = None,
    vault_path: Path,
    exclude_dirs: list[str],
) -> list[RetrievedChunk]:
    """Top-k retrieval over indexed vault notes for ``question``.

    Raises ``OllamaUnavailable`` up front (via ``ensure_models_available``)
    if ``embed_model`` isn't pulled, mirroring ``retrieve_briefing_context``.
    """
    vcfg = _vault_cfg(cfg, vault_path, exclude_dirs)
    olm = make_ollama_client(vcfg)
    ensure_models_available(olm, vcfg.embed_model, embed_model=None)
    coll = make_chroma_collection(vcfg, collection_name=OBSIDIAN_COLLECTION_NAME)
    return Retriever(vcfg, collection=coll, ollama_client=olm).retrieve(question, top_k=top_k)
