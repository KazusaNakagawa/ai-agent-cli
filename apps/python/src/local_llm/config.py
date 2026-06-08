"""既定値 + env override の構成。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TOP_K = 6
DEFAULT_CHUNK_LINES = 40
DEFAULT_CHUNK_OVERLAP = 8
DEFAULT_REPO_ROOT = Path.home() / "work" / "ai-agent"
DEFAULT_CHROMA_REL = Path("apps/python/.chroma_db")
COLLECTION_NAME = "ai_agent_repo"

EXTENSION_ALLOWLIST = {
    ".py", ".ts", ".tsx", ".js", ".md",
    ".json", ".yaml", ".yml", ".sh", ".toml", ".txt",
}
EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".chroma_db",
    ".venv", "dist", "build", ".next",
    "output", "log",  # runtime artifacts, not part of the codebase
}
MAX_FILE_BYTES = 500 * 1024


@dataclass(frozen=True)
class LocalLLMConfig:
    ollama_host: str
    model: str
    embed_model: str
    top_k: int
    repo_root: Path
    chroma_path: Path
    chunk_lines: int
    chunk_overlap: int


def load_config(repo_root: Path | None = None) -> LocalLLMConfig:
    root = (repo_root or Path(os.environ.get("LOCAL_LLM_REPO_ROOT", DEFAULT_REPO_ROOT))).resolve()
    chroma_env = os.environ.get("LOCAL_LLM_CHROMA_PATH")
    chroma_path = Path(chroma_env) if chroma_env else root / DEFAULT_CHROMA_REL
    return LocalLLMConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
        model=os.environ.get("LOCAL_LLM_MODEL", DEFAULT_MODEL),
        embed_model=os.environ.get("LOCAL_LLM_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        top_k=int(os.environ.get("LOCAL_LLM_TOP_K", DEFAULT_TOP_K)),
        repo_root=root,
        chroma_path=chroma_path,
        chunk_lines=DEFAULT_CHUNK_LINES,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )
