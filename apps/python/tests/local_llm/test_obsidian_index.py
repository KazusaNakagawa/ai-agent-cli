"""Tests for Obsidian vault indexing / retrieval (chat RAG).

Same fixture pattern as test_briefing_index.py: in-memory FakeCollection /
FakeOllama routed via monkeypatch, no disk Chroma or real Ollama daemon.
"""
from pathlib import Path

import pytest

from src.local_llm.config import COLLECTION_NAME, OBSIDIAN_COLLECTION_NAME, load_config

from .test_briefing_index import FakeCollection, FakeOllama


@pytest.fixture
def collections(monkeypatch):
    """Route make_chroma_collection() to in-memory FakeCollections keyed by name,
    and make_ollama_client() to a single shared FakeOllama, without touching disk
    or a real Ollama daemon."""
    made: dict[str, FakeCollection] = {}
    olm = FakeOllama()

    def _fake_make_chroma_collection(cfg, collection_name=COLLECTION_NAME):
        return made.setdefault(collection_name, FakeCollection(collection_name))

    import src.local_llm.obsidian_index as obsidian_index

    monkeypatch.setattr(obsidian_index, "make_chroma_collection", _fake_make_chroma_collection)
    monkeypatch.setattr(obsidian_index, "make_ollama_client", lambda cfg: olm)
    return made, olm


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_index_obsidian_indexes_vault_not_repo_root(tmp_path, collections):
    from src.local_llm.obsidian_index import index_obsidian

    made, _ = collections
    vault = tmp_path / "vault"
    _write(vault / "notes" / "idea.md", "# Idea\nsome note\n")
    # A file outside the vault must not be picked up even though it is under repo_root.
    _write(tmp_path / "src" / "unrelated.py", "x = 1\n")

    cfg = load_config(repo_root=tmp_path)
    stats = index_obsidian(cfg, vault_path=vault, exclude_dirs=[])

    assert stats.files == 1
    assert stats.added == 1
    indexed_paths = {r["meta"]["source_path"] for r in made[OBSIDIAN_COLLECTION_NAME].data.values()}
    assert indexed_paths == {"notes/idea.md"}


def test_index_obsidian_skips_exclude_dirs(tmp_path, collections):
    from src.local_llm.obsidian_index import index_obsidian

    made, _ = collections
    vault = tmp_path / "vault"
    _write(vault / "notes" / "keep.md", "keep\n")
    _write(vault / ".obsidian" / "app.json", "{}\n")
    _write(vault / "templates" / "daily.md", "tmpl\n")

    cfg = load_config(repo_root=tmp_path)
    index_obsidian(cfg, vault_path=vault, exclude_dirs=[".obsidian", ".trash", "templates"])

    indexed_paths = {r["meta"]["source_path"] for r in made[OBSIDIAN_COLLECTION_NAME].data.values()}
    assert indexed_paths == {"notes/keep.md"}


def test_retrieve_obsidian_context_queries_obsidian_collection_only(tmp_path, collections):
    from src.local_llm.obsidian_index import index_obsidian, retrieve_obsidian_context

    made, _ = collections
    vault = tmp_path / "vault"
    _write(vault / "notes" / "idea.md", "# Idea\ninvestment thesis\n")

    cfg = load_config(repo_root=tmp_path)
    index_obsidian(cfg, vault_path=vault, exclude_dirs=[])

    chunks = retrieve_obsidian_context(cfg, "thesis?", vault_path=vault, exclude_dirs=[])

    assert len(chunks) == 1
    assert chunks[0].source_path == "notes/idea.md"
    # The repo-code collection was never created by this call.
    assert COLLECTION_NAME not in made


def test_retrieve_obsidian_context_empty_index_returns_no_chunks(tmp_path, collections):
    from src.local_llm.obsidian_index import retrieve_obsidian_context

    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = load_config(repo_root=tmp_path)

    chunks = retrieve_obsidian_context(cfg, "anything?", vault_path=vault, exclude_dirs=[])

    assert chunks == []


def test_retrieve_obsidian_context_raises_ollama_unavailable_when_embed_model_missing(
    tmp_path, monkeypatch
):
    """Mirrors retrieve_briefing_context: an un-pulled embed model must raise
    OllamaUnavailable up front instead of a raw ollama.ResponseError."""
    from src.local_llm.clients import OllamaUnavailable
    from src.local_llm.obsidian_index import retrieve_obsidian_context

    vault = tmp_path / "vault"
    _write(vault / "notes" / "idea.md", "# Idea\n")

    made: dict[str, FakeCollection] = {}
    olm = FakeOllama(pulled_models=())  # embed model not pulled

    def _fake_make_chroma_collection(cfg, collection_name=COLLECTION_NAME):
        return made.setdefault(collection_name, FakeCollection(collection_name))

    import src.local_llm.obsidian_index as obsidian_index

    monkeypatch.setattr(obsidian_index, "make_chroma_collection", _fake_make_chroma_collection)
    monkeypatch.setattr(obsidian_index, "make_ollama_client", lambda cfg: olm)

    cfg = load_config(repo_root=tmp_path)
    with pytest.raises(OllamaUnavailable) as exc:
        retrieve_obsidian_context(cfg, "idea?", vault_path=vault, exclude_dirs=[])
    assert cfg.embed_model in str(exc.value)
