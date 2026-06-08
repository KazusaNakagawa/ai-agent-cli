"""リポジトリ走査 / chunk / 埋め込み / Chroma upsert。"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol


def _extract_embedding(resp) -> list[float]:
    """Accept both dict and Pydantic EmbeddingsResponse from ollama."""
    if isinstance(resp, dict):
        return list(resp["embedding"])
    return list(getattr(resp, "embedding"))

from .config import (
    EXCLUDE_DIRS,
    EXTENSION_ALLOWLIST,
    LocalLLMConfig,
    MAX_FILE_BYTES,
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_path: str
    start_line: int
    end_line: int
    text: str


def iter_source_files(cfg: LocalLLMConfig) -> Iterator[Path]:
    root = cfg.repo_root
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix not in EXTENSION_ALLOWLIST:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def chunk_file(path: Path, cfg: LocalLLMConfig) -> list[Chunk]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return []

    rel = path.relative_to(cfg.repo_root).as_posix()
    step = cfg.chunk_lines - cfg.chunk_overlap
    out: list[Chunk] = []
    i = 0
    while i < len(lines):
        start = i + 1
        end = min(i + cfg.chunk_lines, len(lines))
        body = "\n".join(lines[i:end])
        cid = hashlib.sha256(
            f"{rel}:{start}-{end}:{body}".encode("utf-8")
        ).hexdigest()
        out.append(Chunk(
            chunk_id=cid,
            source_path=rel,
            start_line=start,
            end_line=end,
            text=body,
        ))
        if end >= len(lines):
            break
        i += step
    return out


class _OllamaLike(Protocol):
    def embeddings(self, model: str, prompt: str) -> dict: ...


class _CollectionLike(Protocol):
    def get(self, ids=None, where=None, include=None) -> dict: ...
    def upsert(self, ids, embeddings, documents, metadatas) -> None: ...
    def delete(self, ids=None, where=None) -> None: ...


@dataclass
class IndexStats:
    files: int = 0
    chunks: int = 0
    added: int = 0
    updated: int = 0
    deleted: int = 0


class Indexer:
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

    def run(self) -> IndexStats:
        stats = IndexStats()
        seen_files: set[str] = set()

        for path in iter_source_files(self.cfg):
            chunks = chunk_file(path, self.cfg)
            if not chunks:
                continue
            stats.files += 1
            stats.chunks += len(chunks)

            rel = chunks[0].source_path
            seen_files.add(rel)
            current_ids = {c.chunk_id for c in chunks}

            existing = set(self.collection.get(
                where={"source_path": rel}
            ).get("ids", []))
            new_chunks = [c for c in chunks if c.chunk_id not in existing]
            stale_ids = [i for i in existing if i not in current_ids]

            if new_chunks:
                embedded: list[tuple[Chunk, list[float]]] = []
                for c in new_chunks:
                    try:
                        resp = self.ollama.embeddings(
                            model=self.cfg.embed_model,
                            prompt=c.text,
                        )
                    except Exception as e:
                        # Skip only when the error looks like a context-window
                        # overflow; #138 (AST chunking) will reduce these cases.
                        # Anything else (network/auth/etc.) re-raises so the run
                        # fails loudly instead of silently dropping data.
                        msg = str(e).lower()
                        if not any(k in msg for k in (
                            "context", "exceed", "token", "length", "too long"
                        )):
                            raise
                        print(
                            f"  skip {c.source_path}:{c.start_line}-{c.end_line} "
                            f"({type(e).__name__}: {e})",
                            file=sys.stderr,
                        )
                        continue
                    embedded.append((c, _extract_embedding(resp)))

                if embedded:
                    self.collection.upsert(
                        ids=[c.chunk_id for c, _ in embedded],
                        embeddings=[v for _, v in embedded],
                        documents=[c.text for c, _ in embedded],
                        metadatas=[
                            {
                                "source_path": c.source_path,
                                "start_line": c.start_line,
                                "end_line": c.end_line,
                            }
                            for c, _ in embedded
                        ],
                    )
                    if existing:
                        stats.updated += len(embedded)
                    else:
                        stats.added += len(embedded)

            if stale_ids:
                self.collection.delete(ids=stale_ids)
                stats.deleted += len(stale_ids)

        # stats.deleted counts chunks (same unit as added/updated). For whole-file
        # deletions we count every chunk that lived under that source_path.
        all_data = self.collection.get(include=["metadatas"])
        all_ids = all_data.get("ids", [])
        all_metas = all_data.get("metadatas", []) or []
        deleted_paths: set[str] = set()
        for cid, meta in zip(all_ids, all_metas, strict=True):
            sp = meta.get("source_path") if isinstance(meta, dict) else None
            if sp and sp not in seen_files:
                deleted_paths.add(sp)
        for sp in deleted_paths:
            ids_for_path = [
                cid for cid, m in zip(all_ids, all_metas, strict=True)
                if isinstance(m, dict) and m.get("source_path") == sp
            ]
            self.collection.delete(where={"source_path": sp})
            stats.deleted += len(ids_for_path)

        return stats
