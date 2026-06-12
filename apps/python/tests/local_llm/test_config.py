import os
from pathlib import Path

from src.local_llm.config import LocalLLMConfig, load_config


def test_load_config_defaults(monkeypatch, tmp_path):
    for key in [
        "OLLAMA_HOST",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_EMBED_MODEL",
        "LOCAL_LLM_NUM_CTX",
        "LOCAL_LLM_TEMPERATURE",
        "LOCAL_LLM_TOP_K",
        "LOCAL_LLM_CHROMA_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg = load_config(repo_root=tmp_path)

    assert isinstance(cfg, LocalLLMConfig)
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.model == "qwen2.5:14b"
    assert cfg.embed_model == "bge-m3"
    assert cfg.num_ctx == 16384
    assert cfg.temperature == 0.2
    assert cfg.top_k == 6
    assert cfg.repo_root == tmp_path
    assert cfg.chunk_lines == 40
    assert cfg.chunk_overlap == 8
    assert cfg.chroma_path.name == ".chroma_db"


def test_load_config_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_HOST", "http://example:11434")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:32b")
    monkeypatch.setenv("LOCAL_LLM_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("LOCAL_LLM_NUM_CTX", "32768")
    monkeypatch.setenv("LOCAL_LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("LOCAL_LLM_TOP_K", "10")
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "custom_chroma"))

    cfg = load_config(repo_root=tmp_path)

    assert cfg.ollama_host == "http://example:11434"
    assert cfg.model == "qwen2.5:32b"
    assert cfg.embed_model == "nomic-embed-text"
    assert cfg.num_ctx == 32768
    assert cfg.temperature == 0.7
    assert cfg.top_k == 10
    assert cfg.chroma_path == tmp_path / "custom_chroma"


def test_load_config_falls_back_on_malformed_numeric_env(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("LOCAL_LLM_NUM_CTX", "abc")
    monkeypatch.setenv("LOCAL_LLM_TEMPERATURE", "warm")

    with caplog.at_level("WARNING", logger="src.local_llm.config"):
        cfg = load_config(repo_root=tmp_path)

    # 不正値はクラッシュせず既定値にフォールバックし、warning に残す
    assert cfg.num_ctx == 16384
    assert cfg.temperature == 0.2
    messages = [r.getMessage() for r in caplog.records]
    assert any("LOCAL_LLM_NUM_CTX" in m for m in messages)
    assert any("LOCAL_LLM_TEMPERATURE" in m for m in messages)
