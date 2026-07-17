from pathlib import Path

import pytest

from src.local_llm.config import BRIEFING_COLLECTION_NAME, COLLECTION_NAME, load_config


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.data: dict[str, dict] = {}

    def get(self, ids=None, where=None, include=None):
        if ids is not None:
            existing = [i for i in ids if i in self.data]
            return {"ids": existing}
        if where and "source_path" in where:
            sp = where["source_path"]
            ids_match = [i for i, r in self.data.items() if r["meta"]["source_path"] == sp]
            return {"ids": ids_match}
        ids_all = list(self.data.keys())
        if include and "metadatas" in include:
            return {"ids": ids_all, "metadatas": [self.data[i]["meta"] for i in ids_all]}
        return {"ids": ids_all}

    def upsert(self, ids, embeddings, documents, metadatas):
        for i, e, d, m in zip(ids, embeddings, documents, metadatas, strict=True):
            self.data[i] = {"embedding": e, "document": d, "meta": m}

    def delete(self, ids=None, where=None):
        target: list[str] = []
        if ids:
            target.extend(ids)
        if where and "source_path" in where:
            sp = where["source_path"]
            target.extend(i for i, r in self.data.items() if r["meta"]["source_path"] == sp)
        for i in set(target):
            self.data.pop(i, None)

    def query(self, query_embeddings, n_results):
        items = list(self.data.items())[:n_results]
        return {
            "documents": [[r["document"] for _, r in items]],
            "metadatas": [[r["meta"] for _, r in items]],
            "distances": [[0.1 * i for i in range(len(items))]],
        }


class FakeOllama:
    def __init__(self, pulled_models=("bge-m3",)):
        self.calls = 0
        self._pulled_models = set(pulled_models)

    def embeddings(self, model, prompt):
        self.calls += 1
        return {"embedding": [float(len(prompt) % 7), float(self.calls)]}

    def list(self):
        return {"models": [{"name": m} for m in self._pulled_models]}


@pytest.fixture
def collections(monkeypatch):
    """Route make_chroma_collection() to in-memory FakeCollections keyed by name,
    and make_ollama_client() to a single shared FakeOllama, without touching disk
    or a real Ollama daemon."""
    made: dict[str, FakeCollection] = {}
    olm = FakeOllama()

    def _fake_make_chroma_collection(cfg, collection_name=COLLECTION_NAME):
        return made.setdefault(collection_name, FakeCollection(collection_name))

    def _fake_make_ollama_client(cfg):
        return olm

    import src.local_llm.briefing_index as briefing_index

    monkeypatch.setattr(briefing_index, "make_chroma_collection", _fake_make_chroma_collection)
    monkeypatch.setattr(briefing_index, "make_ollama_client", _fake_make_ollama_client)
    return made, olm


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_index_briefings_indexes_briefing_dir_not_repo_root(tmp_path, collections):
    from src.local_llm.briefing_index import index_briefings

    made, _ = collections
    briefing_dir = tmp_path / "output" / "briefing"
    _write(briefing_dir / "briefing_2026-07-01.md", "# July 1\nNVDA up 3%\n")
    _write(briefing_dir / "briefing_2026-07-02.md", "# July 2\nNVDA down 1%\n")
    # A file outside the briefing dir must not be picked up.
    _write(tmp_path / "src" / "unrelated.py", "x = 1\n")
    # Session id files (no extension) inside .sessions/ must be skipped.
    _write(briefing_dir / ".sessions" / "2026-07-01", "some-uuid")

    cfg = load_config(repo_root=tmp_path)
    stats = index_briefings(cfg, briefing_dir=briefing_dir)

    assert stats.files == 2
    assert stats.added == 2
    assert made[BRIEFING_COLLECTION_NAME].data
    indexed_paths = {r["meta"]["source_path"] for r in made[BRIEFING_COLLECTION_NAME].data.values()}
    assert indexed_paths == {"briefing_2026-07-01.md", "briefing_2026-07-02.md"}


def test_index_briefings_is_incremental(tmp_path, collections):
    from src.local_llm.briefing_index import index_briefings

    made, olm = collections
    briefing_dir = tmp_path / "output" / "briefing"
    _write(briefing_dir / "briefing_2026-07-01.md", "# July 1\n")

    cfg = load_config(repo_root=tmp_path)
    index_briefings(cfg, briefing_dir=briefing_dir)
    calls_after_first = olm.calls

    # Re-running with no new content must not re-embed anything.
    stats2 = index_briefings(cfg, briefing_dir=briefing_dir)
    assert stats2.added == 0
    assert olm.calls == calls_after_first


def test_retrieve_briefing_context_queries_briefing_collection_only(tmp_path, collections):
    from src.local_llm.briefing_index import index_briefings, retrieve_briefing_context

    made, _ = collections
    briefing_dir = tmp_path / "output" / "briefing"
    _write(briefing_dir / "briefing_2026-07-01.md", "# July 1\nNVDA news\n")

    cfg = load_config(repo_root=tmp_path)
    index_briefings(cfg, briefing_dir=briefing_dir)

    chunks = retrieve_briefing_context(cfg, "NVDA?", briefing_dir=briefing_dir)

    assert len(chunks) == 1
    assert chunks[0].source_path == "briefing_2026-07-01.md"
    # The repo-code collection was never created by this call.
    assert COLLECTION_NAME not in made


def test_retrieve_briefing_context_empty_index_returns_no_chunks(tmp_path, collections):
    from src.local_llm.briefing_index import retrieve_briefing_context

    briefing_dir = tmp_path / "output" / "briefing"
    briefing_dir.mkdir(parents=True)
    cfg = load_config(repo_root=tmp_path)

    chunks = retrieve_briefing_context(cfg, "anything?", briefing_dir=briefing_dir)

    assert chunks == []


def test_retrieve_briefing_context_raises_ollama_unavailable_when_embed_model_missing(
    tmp_path, monkeypatch
):
    """A `POST /api/chat` with search_history must surface a clean,
    actionable error (mapped to 503 by the router) instead of letting a raw
    ollama.ResponseError ("model not found") bubble up as a 500 (regression
    reported after #395 shipped).
    """
    from src.local_llm.briefing_index import retrieve_briefing_context
    from src.local_llm.clients import OllamaUnavailable

    briefing_dir = tmp_path / "output" / "briefing"
    _write(briefing_dir / "briefing_2026-07-01.md", "# July 1\n")

    made: dict[str, FakeCollection] = {}
    olm = FakeOllama(pulled_models=())  # embed model not pulled

    def _fake_make_chroma_collection(cfg, collection_name=COLLECTION_NAME):
        return made.setdefault(collection_name, FakeCollection(collection_name))

    import src.local_llm.briefing_index as briefing_index

    monkeypatch.setattr(briefing_index, "make_chroma_collection", _fake_make_chroma_collection)
    monkeypatch.setattr(briefing_index, "make_ollama_client", lambda cfg: olm)

    cfg = load_config(repo_root=tmp_path)
    with pytest.raises(OllamaUnavailable) as exc:
        retrieve_briefing_context(cfg, "NVDA?", briefing_dir=briefing_dir)
    assert cfg.embed_model in str(exc.value)
