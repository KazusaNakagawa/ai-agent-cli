"""Defaults + env-override configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
# qwen2.5:14b follows tool calling far better than qwen2.5:7b, which is needed
# to reliably trigger web_search on the `--briefing` path. ~8.5GB RAM at Q4.
# To go back to a smaller model, override with env LOCAL_LLM_MODEL=qwen2.5:7b.
DEFAULT_MODEL = "qwen2.5:14b"
# bge-m3 (1024d) outperforms nomic-embed-text (768d) on Japanese + code retrieval
# (#135). Switching changes embedding dimensions, so an existing .chroma_db built
# with the previous default must be rebuilt: bin/local_llm.sh --index --reset.
DEFAULT_EMBED_MODEL = "bge-m3"
# Ollama's default num_ctx (4096) silently truncates the tail of the prompt once
# pre-fetched context is injected (#150). qwen2.5:14b Q4 + 16K ctx runs fine on 24GB RAM.
DEFAULT_NUM_CTX = 16384
# Fact-transcription / summarization task, so a low temperature is used to
# prioritize faithful citation.
DEFAULT_TEMPERATURE = 0.2
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
    num_ctx: int
    temperature: float
    top_k: int
    repo_root: Path
    chroma_path: Path
    chunk_lines: int
    chunk_overlap: int


def _env_number(name: str, default, cast):
    """Convert an env var to a number. On an invalid value, warn and fall back to the default.

    For the batch (cron) path it is operationally safer to keep running with the
    default and log it than to crash on every startup because of a typo'd env var
    (Sourcery / CodeRabbit feedback).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning(
            "env %s=%r を %s に変換できないため既定値 %r を使用",
            name,
            raw,
            cast.__name__,
            default,
        )
        return default


def load_config(repo_root: Path | None = None) -> LocalLLMConfig:
    root = (repo_root or Path(os.environ.get("LOCAL_LLM_REPO_ROOT", DEFAULT_REPO_ROOT))).resolve()
    chroma_env = os.environ.get("LOCAL_LLM_CHROMA_PATH")
    chroma_path = Path(chroma_env) if chroma_env else root / DEFAULT_CHROMA_REL
    return LocalLLMConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
        model=os.environ.get("LOCAL_LLM_MODEL", DEFAULT_MODEL),
        embed_model=os.environ.get("LOCAL_LLM_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        num_ctx=_env_number("LOCAL_LLM_NUM_CTX", DEFAULT_NUM_CTX, int),
        temperature=_env_number("LOCAL_LLM_TEMPERATURE", DEFAULT_TEMPERATURE, float),
        top_k=_env_number("LOCAL_LLM_TOP_K", DEFAULT_TOP_K, int),
        repo_root=root,
        chroma_path=chroma_path,
        chunk_lines=DEFAULT_CHUNK_LINES,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )
