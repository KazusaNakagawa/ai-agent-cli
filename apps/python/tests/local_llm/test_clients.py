import pytest

from src.local_llm.clients import (
    EmbedModelMismatch,
    OllamaUnavailable,
    delete_collection,
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
        synthesis_model="qwen2.5:14b",
        embed_model=embed_model,
        num_ctx=16384,
        temperature=0.2,
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


def test_make_chroma_collection_uses_custom_collection_name(tmp_path):
    """A non-default collection_name creates/reuses a separate collection in
    the same chroma_path, so repo-code and briefing indexes don't mix (#395).
    """
    chroma_path = tmp_path / "chroma"
    cfg = _make_cfg(chroma_path, "bge-m3")

    repo_coll = make_chroma_collection(cfg)
    briefing_coll = make_chroma_collection(cfg, collection_name="ai_agent_briefings")

    assert repo_coll.name != briefing_coll.name
    assert (briefing_coll.metadata or {}).get("embed_model") == "bge-m3"


def test_make_chroma_collection_custom_name_checks_embed_mismatch_independently(tmp_path):
    """The mismatch check is per-collection: a briefing collection built with
    a different embed_model than the repo collection must still raise.
    """
    chroma_path = tmp_path / "chroma"
    make_chroma_collection(_make_cfg(chroma_path, "bge-m3"), collection_name="ai_agent_briefings")

    cfg_after_switch = _make_cfg(chroma_path, "nomic-embed-text")
    with pytest.raises(EmbedModelMismatch):
        make_chroma_collection(cfg_after_switch, collection_name="ai_agent_briefings")


def test_delete_collection_removes_only_the_named_collection(tmp_path):
    chroma_path = tmp_path / "chroma"
    cfg = _make_cfg(chroma_path, "bge-m3")
    repo_coll = make_chroma_collection(cfg)
    make_chroma_collection(cfg, collection_name="ai_agent_briefings")

    delete_collection(cfg, "ai_agent_briefings")

    # The other collection survives, and the deleted one comes back empty
    # (get_or_create) rather than raising.
    import chromadb
    client = chromadb.PersistentClient(path=str(chroma_path))
    assert {c.name for c in client.list_collections()} == {repo_coll.name}


def test_delete_collection_is_a_noop_when_missing(tmp_path):
    chroma_path = tmp_path / "chroma"
    cfg = _make_cfg(chroma_path, "bge-m3")
    make_chroma_collection(cfg)  # only the repo collection exists

    delete_collection(cfg, "ai_agent_briefings")  # must not raise


def test_delete_collection_is_a_noop_when_chroma_path_missing(tmp_path):
    cfg = _make_cfg(tmp_path / "never_created", "bge-m3")

    delete_collection(cfg, "ai_agent_briefings")  # must not raise


def test_make_chroma_collection_reuses_legacy_index_when_embed_unchanged(tmp_path):
    """Pre-#135 collections (no embed_model metadata) must remain usable when
    the operator keeps nomic-embed-text — legacy is treated as nomic, not
    rejected with EmbedModelMismatch.
    """
    import chromadb

    from src.local_llm.config import COLLECTION_NAME

    chroma_path = tmp_path / "chroma"
    chroma_path.mkdir()
    client = chromadb.PersistentClient(path=str(chroma_path))
    client.create_collection(COLLECTION_NAME)  # no metadata, like a legacy index

    cfg = _make_cfg(chroma_path, "nomic-embed-text")
    # Must not raise; legacy index is treated as nomic-embed-text.
    make_chroma_collection(cfg)
