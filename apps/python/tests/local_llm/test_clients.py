import pytest

from src.local_llm.clients import OllamaUnavailable, ensure_models_available


class StubClient:
    def __init__(self, models):
        self._models = models

    def list(self):
        return {"models": [{"name": m} for m in self._models]}


def test_ensure_models_available_ok():
    ensure_models_available(StubClient(["qwen2.5:7b", "nomic-embed-text"]), "qwen2.5:7b", "nomic-embed-text")


def test_ensure_models_available_accepts_implicit_latest_tag():
    ensure_models_available(
        StubClient(["qwen2.5:7b", "nomic-embed-text:latest"]),
        "qwen2.5:7b",
        "nomic-embed-text",
    )


def test_ensure_models_available_missing_model():
    with pytest.raises(OllamaUnavailable) as exc:
        ensure_models_available(StubClient(["nomic-embed-text"]), "qwen2.5:7b", "nomic-embed-text")
    assert "qwen2.5:7b" in str(exc.value)


def test_ensure_models_available_connection_failure():
    class Broken:
        def list(self):
            raise ConnectionError("refused")

    with pytest.raises(OllamaUnavailable) as exc:
        ensure_models_available(Broken(), "qwen2.5:7b", "nomic-embed-text")
    assert "ollama serve" in str(exc.value)
