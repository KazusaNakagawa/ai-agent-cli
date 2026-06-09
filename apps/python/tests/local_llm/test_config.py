import os
from pathlib import Path

from src.local_llm.config import LocalLLMConfig, load_config


def test_load_config_defaults(monkeypatch, tmp_path):
    for key in [
        "OLLAMA_HOST",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_EMBED_MODEL",
        "LOCAL_LLM_TOP_K",
        "LOCAL_LLM_CHROMA_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg = load_config(repo_root=tmp_path)

    assert isinstance(cfg, LocalLLMConfig)
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.model == "qwen2.5:14b"
    assert cfg.embed_model == "nomic-embed-text"
    assert cfg.top_k == 6
    assert cfg.repo_root == tmp_path
    assert cfg.chunk_lines == 40
    assert cfg.chunk_overlap == 8
    assert cfg.chroma_path.name == ".chroma_db"


def test_load_config_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_HOST", "http://example:11434")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:32b")
    monkeypatch.setenv("LOCAL_LLM_EMBED_MODEL", "bge-m3")
    monkeypatch.setenv("LOCAL_LLM_TOP_K", "10")
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "custom_chroma"))

    cfg = load_config(repo_root=tmp_path)

    assert cfg.ollama_host == "http://example:11434"
    assert cfg.model == "qwen2.5:32b"
    assert cfg.embed_model == "bge-m3"
    assert cfg.top_k == 10
    assert cfg.chroma_path == tmp_path / "custom_chroma"
