"""既定値 + env override の構成。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
# qwen2.5:14b は qwen2.5:7b に比べて tool calling 追従が格段に良く、
# `--briefing` 経路で web_search を確実に呼ぶために必要。Q4 量子化で ~8.5GB RAM。
# 小さいモデルに戻したい場合は env LOCAL_LLM_MODEL=qwen2.5:7b で override 可能。
DEFAULT_MODEL = "qwen2.5:14b"
# bge-m3 (1024d) outperforms nomic-embed-text (768d) on Japanese + code retrieval
# (#135). Switching changes embedding dimensions, so an existing .chroma_db built
# with the previous default must be rebuilt: bin/local_llm.sh --index --reset.
DEFAULT_EMBED_MODEL = "bge-m3"
# Ollama 既定の num_ctx (4096) では pre-fetch 注入済みプロンプトの末尾が黙って
# 切り捨てられる (#150)。qwen2.5:14b Q4 + 16K ctx は 24GB RAM で問題なく動く。
DEFAULT_NUM_CTX = 16384
# 事実の転記・要約タスクなので低温度で引用追従を優先する。
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
    """env を数値に変換する。不正値は warning を出して既定値にフォールバック。

    バッチ (cron) 経路で typo った env のせいに起動ごと落とすより、既定値で
    動かしてログに残す方が運用上安全 (Sourcery / CodeRabbit 指摘)。
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
