import pytest

from src.local_llm.clients import (
    EmbedModelMismatch,
    OllamaUnavailable,
    ensure_models_available,
    make_chroma_collection,
)
from src.local_llm.config import LocalLLMConfig


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


def test_ensure_models_available_accepts_pydantic_model_objects():
    """Real ollama client returns Pydantic ListResponse with `.model` attr."""

    class FakeModel:
        def __init__(self, name):
            self.model = name

    class FakeResp:
        def __init__(self, names):
            self.models = [FakeModel(n) for n in names]

    class PydanticClient:
        def list(self):
            return FakeResp(["qwen2.5:7b", "nomic-embed-text:latest"])

    ensure_models_available(PydanticClient(), "qwen2.5:7b", "nomic-embed-text")


def test_ensure_models_available_missing_model():
    with pytest.raises(OllamaUnavailable) as exc:
        ensure_models_available(StubClient(["nomic-embed-text"]), "qwen2.5:7b", "nomic-embed-text")
    assert "qwen2.5:7b" in str(exc.value)


def test_ensure_models_available_skips_embed_when_none():
    # --briefing path only needs the generation model; embed_model=None should
    # not trigger a "nomic-embed-text not found" failure.
    ensure_models_available(StubClient(["qwen2.5:7b"]), "qwen2.5:7b", embed_model=None)


def test_ensure_models_available_still_validates_generation_when_embed_none():
    with pytest.raises(OllamaUnavailable) as exc:
        ensure_models_available(StubClient([]), "qwen2.5:7b", embed_model=None)
    assert "qwen2.5:7b" in str(exc.value)


def test_ensure_models_available_connection_failure():
    class Broken:
        def list(self):
            raise ConnectionError("refused")

    with pytest.raises(OllamaUnavailable) as exc:
        ensure_models_available(Broken(), "qwen2.5:7b", "nomic-embed-text")
    assert "ollama serve" in str(exc.value)


def _make_cfg(chroma_path, embed_model):
    return LocalLLMConfig(
        ollama_host="http://localhost:11434",
        model="qwen2.5:14b",
        embed_model=embed_model,
        top_k=6,
        repo_root=chroma_path.parent,
        chroma_path=chroma_path,
        chunk_lines=40,
        chunk_overlap=8,
    )


def test_make_chroma_collection_tags_metadata_on_create(tmp_path):
    cfg = _make_cfg(tmp_path / "chroma", "bge-m3")

    coll = make_chroma_collection(cfg)

    assert (coll.metadata or {}).get("embed_model") == "bge-m3"


def test_make_chroma_collection_reuses_matching_collection(tmp_path):
    chroma_path = tmp_path / "chroma"
    cfg = _make_cfg(chroma_path, "bge-m3")

    make_chroma_collection(cfg)
    # Second call must succeed (same embed_model) and not raise.
    coll = make_chroma_collection(cfg)
    assert (coll.metadata or {}).get("embed_model") == "bge-m3"


def test_make_chroma_collection_raises_on_embed_model_mismatch(tmp_path):
    chroma_path = tmp_path / "chroma"
    make_chroma_collection(_make_cfg(chroma_path, "bge-m3"))

    cfg_after_switch = _make_cfg(chroma_path, "nomic-embed-text")
    with pytest.raises(EmbedModelMismatch) as exc:
        make_chroma_collection(cfg_after_switch)
    assert "bge-m3" in str(exc.value)
    assert "--reset" in str(exc.value)


def test_make_chroma_collection_treats_pre_135_index_as_nomic(tmp_path):
    """Collections built before #135 carry no embed_model tag and must be
    treated as nomic-embed-text so a silent switch to bge-m3 is caught.
    """
    import chromadb

    from src.local_llm.config import COLLECTION_NAME

    chroma_path = tmp_path / "chroma"
    chroma_path.mkdir()
    client = chromadb.PersistentClient(path=str(chroma_path))
    client.create_collection(COLLECTION_NAME)  # no metadata, like a legacy index

    cfg = _make_cfg(chroma_path, "bge-m3")
    with pytest.raises(EmbedModelMismatch) as exc:
        make_chroma_collection(cfg)
    assert "nomic-embed-text" in str(exc.value)
