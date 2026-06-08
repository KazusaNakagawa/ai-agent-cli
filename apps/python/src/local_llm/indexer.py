"""リポジトリ走査 / chunk / 埋め込み / Chroma upsert。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

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
