from pathlib import Path

from src.local_llm.config import load_config
from src.local_llm.indexer import Chunk, chunk_file, iter_source_files


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_iter_source_files_filters_excluded_and_extensions(tmp_path):
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _write(tmp_path / "README.md", "# hi\n")
    _write(tmp_path / "node_modules" / "skip.js", "nope\n")
    _write(tmp_path / "image.png", "binary")
    big = tmp_path / "big.py"
    big.write_text("x\n" * 300_000)  # > 500KB

    cfg = load_config(repo_root=tmp_path)
    found = sorted(p.relative_to(tmp_path).as_posix() for p in iter_source_files(cfg))

    assert found == ["README.md", "src/a.py"]


def test_chunk_file_splits_with_overlap(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("\n".join(f"line{i}" for i in range(150)) + "\n")

    cfg = load_config(repo_root=tmp_path)
    chunks = chunk_file(f, cfg)

    assert all(isinstance(c, Chunk) for c in chunks)
    # 60 lines / 10 overlap → starts at 1, 51, 101, ...
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 60
    assert chunks[1].start_line == 51
    assert chunks[1].end_line == 110
    assert chunks[-1].end_line >= 150
    assert chunks[0].source_path == "x.py"
    assert "line0" in chunks[0].text


def test_chunk_file_short_file_one_chunk(tmp_path):
    f = tmp_path / "short.py"
    f.write_text("a\nb\nc\n")
    cfg = load_config(repo_root=tmp_path)
    chunks = chunk_file(f, cfg)
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3


def test_chunk_file_chunk_id_changes_with_content(tmp_path):
    f = tmp_path / "c.py"
    f.write_text("hello\n")
    cfg = load_config(repo_root=tmp_path)
    id1 = chunk_file(f, cfg)[0].chunk_id

    f.write_text("hello world\n")
    id2 = chunk_file(f, cfg)[0].chunk_id

    assert id1 != id2


class FakeCollection:
    def __init__(self):
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
        for i, e, d, m in zip(ids, embeddings, documents, metadatas):
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


class FakeOllama:
    def __init__(self):
        self.calls = 0

    def embeddings(self, model, prompt):
        self.calls += 1
        v = [float(len(prompt) % 7), float(self.calls)]
        return {"embedding": v}


def test_indexer_run_adds_new_and_skips_unchanged(tmp_path):
    from src.local_llm.indexer import Indexer

    (tmp_path / "a.py").write_text("alpha\n")
    (tmp_path / "b.md").write_text("# beta\n")
    cfg = load_config(repo_root=tmp_path)
    coll = FakeCollection()
    olm = FakeOllama()
    idx = Indexer(cfg, collection=coll, ollama_client=olm)

    stats = idx.run()
    assert stats.files == 2
    assert stats.added == 2
    assert stats.updated == 0
    assert stats.deleted == 0
    assert olm.calls == 2

    olm2 = FakeOllama()
    idx2 = Indexer(cfg, collection=coll, ollama_client=olm2)
    stats2 = idx2.run()
    assert stats2.added == 0
    assert stats2.updated == 0
    assert olm2.calls == 0


def test_indexer_detects_modified_and_deleted(tmp_path):
    from src.local_llm.indexer import Indexer

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("v1\n")
    b.write_text("hello\n")
    cfg = load_config(repo_root=tmp_path)
    coll = FakeCollection()

    Indexer(cfg, collection=coll, ollama_client=FakeOllama()).run()

    a.write_text("v2\n")
    b.unlink()

    olm = FakeOllama()
    stats = Indexer(cfg, collection=coll, ollama_client=olm).run()
    assert stats.added >= 1
    assert stats.deleted >= 1

    remaining = [r["meta"]["source_path"] for r in coll.data.values()]
    assert "b.py" not in remaining
