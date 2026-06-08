from src.local_llm.config import load_config
from src.local_llm.retriever import RetrievedChunk, Retriever, build_context_text


def test_build_context_text_formats_sections():
    chunks = [
        RetrievedChunk(source_path="a.py", start_line=1, end_line=10, text="A body", distance=0.1),
        RetrievedChunk(source_path="b.md", start_line=5, end_line=12, text="B body", distance=0.3),
    ]
    out = build_context_text(chunks)
    assert "[a.py:1-10]" in out
    assert "A body" in out
    assert "[b.md:5-12]" in out
    assert "---" in out


class FakeCollection:
    def __init__(self, hits):
        self._hits = hits
        self.queried_with = None

    def query(self, query_embeddings, n_results):
        self.queried_with = (query_embeddings, n_results)
        return self._hits


class FakeOllama:
    def __init__(self, tokens):
        self._tokens = tokens

    def embeddings(self, model, prompt):
        return {"embedding": [0.1, 0.2]}

    def generate(self, model, prompt, stream):
        assert stream is True
        for t in self._tokens:
            yield {"response": t, "done": False}
        yield {"response": "", "done": True}


def test_retriever_retrieve_returns_top_k(tmp_path):
    hits = {
        "ids": [["c1", "c2"]],
        "documents": [["doc1", "doc2"]],
        "metadatas": [[
            {"source_path": "a.py", "start_line": 1, "end_line": 10},
            {"source_path": "b.py", "start_line": 20, "end_line": 30},
        ]],
        "distances": [[0.1, 0.2]],
    }
    cfg = load_config(repo_root=tmp_path)
    r = Retriever(cfg, collection=FakeCollection(hits), ollama_client=FakeOllama([]))
    out = r.retrieve("質問", top_k=2)
    assert [c.source_path for c in out] == ["a.py", "b.py"]
    assert out[0].text == "doc1"
    assert out[1].start_line == 20


def test_retriever_generate_streams_tokens(tmp_path):
    hits = {
        "ids": [["c1"]],
        "documents": [["alpha"]],
        "metadatas": [[{"source_path": "a.py", "start_line": 1, "end_line": 5}]],
        "distances": [[0.1]],
    }
    cfg = load_config(repo_root=tmp_path)
    r = Retriever(cfg, collection=FakeCollection(hits), ollama_client=FakeOllama(["Hel", "lo"]))
    chunks = r.retrieve("Q", top_k=1)
    tokens = list(r.generate("Q", chunks))
    assert "".join(tokens) == "Hello"


def test_retriever_retrieve_handles_empty(tmp_path):
    empty = {
        "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]],
    }
    cfg = load_config(repo_root=tmp_path)
    r = Retriever(cfg, collection=FakeCollection(empty), ollama_client=FakeOllama([]))
    assert r.retrieve("Q", top_k=3) == []
