# Local LLM RAG Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Issue #140 — `apps/python/src/local_llm/` 配下に Ollama + Chroma の最小 RAG サブシステムを立て、`python -m local_llm` でリポジトリを index/ask できる CLI を提供する。

**Architecture:** `config` (defaults + env) → `indexer` (walk → chunk → embed → Chroma upsert) → `retriever` (embed query → Chroma.query → ollama.generate stream)。各層は単一責務でテスト時に stub 差替え可能。CLI は argparse の薄いラッパ。

**Tech Stack:** Python 3.12 / Ollama Python client / chromadb / pytest / argparse

**Spec:** `docs/superpowers/specs/2026-06-08-local-llm-bootstrap-design.md`

**Branch:** `feature/issue-140-local-llm-bootstrap`（既に存在し spec をコミット済み）

---

## File Structure

| Path | Responsibility |
|---|---|
| `apps/python/src/local_llm/__init__.py` | Public exports (`Indexer`, `Retriever`, `load_config`) |
| `apps/python/src/local_llm/__main__.py` | `python -m local_llm` → `cli.main()` |
| `apps/python/src/local_llm/config.py` | 既定値 + env override の dataclass |
| `apps/python/src/local_llm/indexer.py` | walk / chunk / embed / Chroma upsert / 削除検出 |
| `apps/python/src/local_llm/retriever.py` | embed query / Chroma.query / context text 整形 / ollama.generate stream |
| `apps/python/src/local_llm/cli.py` | argparse: `--index` `--ask` `--sources` `--status` `--reset` |
| `apps/python/bin/local_llm.sh` | venv 検出 → `python -m local_llm "$@"`（chat.sh と同形） |
| `bin/local_llm.sh` | ルート薄ラッパ |
| `apps/python/tests/local_llm/test_config.py` | env override / 既定値 |
| `apps/python/tests/local_llm/test_indexer.py` | chunk_file / 走査 / hash skip / 削除検出 |
| `apps/python/tests/local_llm/test_retriever.py` | build_context_text / retrieve / generate stub |
| `apps/python/tests/local_llm/test_cli.py` | `--status` `--sources` の引数解析と出力 |
| `apps/python/requirements.in` | `chromadb>=0.5`, `ollama>=0.3` 追加 |
| `.gitignore` | `apps/python/.chroma_db/` 追加 |
| `README.md` | "Local LLM (experimental)" セクション追加 |

---

## Task 1: 依存と .gitignore を追加

**Files:**
- Modify: `apps/python/requirements.in`
- Modify: `.gitignore`
- Regenerate: `apps/python/requirements.txt`

- [ ] **Step 1: `requirements.in` を編集**

`apps/python/requirements.in` の末尾に追記:

```text
# Local LLM (experimental)
chromadb>=0.5
ollama>=0.3
```

- [ ] **Step 2: `.gitignore` を編集**

`.gitignore` の末尾に追記:

```text
# Local LLM RAG persistent store
apps/python/.chroma_db/
```

- [ ] **Step 3: requirements.txt を再生成**

```bash
cd apps/python && uv pip compile requirements.in -o requirements.txt
```

期待: 差分に `chromadb`, `ollama` とその推移依存が現れる。

- [ ] **Step 4: 依存を sync**

```bash
cd apps/python && uv pip sync requirements.txt
```

- [ ] **Step 5: Commit**

```bash
git add apps/python/requirements.in apps/python/requirements.txt .gitignore
git commit -m "chore(local-llm): add chromadb + ollama deps and ignore chroma store"
```

---

## Task 2: `config.py` を実装

**Files:**
- Create: `apps/python/src/local_llm/__init__.py`
- Create: `apps/python/src/local_llm/config.py`
- Create: `apps/python/tests/local_llm/__init__.py`
- Create: `apps/python/tests/local_llm/test_config.py`

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_config.py`:

```python
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
    assert cfg.model == "qwen2.5:7b"
    assert cfg.embed_model == "nomic-embed-text"
    assert cfg.top_k == 6
    assert cfg.repo_root == tmp_path
    assert cfg.chunk_lines == 60
    assert cfg.chunk_overlap == 10
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
```

- [ ] **Step 2: 実行して失敗を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_config.py -v
```

期待: `ModuleNotFoundError: No module named 'src.local_llm'` で FAIL。

- [ ] **Step 3: `__init__.py` と `config.py` を実装**

`apps/python/src/local_llm/__init__.py`:

```python
from .config import LocalLLMConfig, load_config

__all__ = ["LocalLLMConfig", "load_config"]
```

`apps/python/tests/local_llm/__init__.py`: 空ファイル。

`apps/python/src/local_llm/config.py`:

```python
"""既定値 + env override の構成。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TOP_K = 6
DEFAULT_CHUNK_LINES = 60
DEFAULT_CHUNK_OVERLAP = 10
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
}
MAX_FILE_BYTES = 500 * 1024


@dataclass(frozen=True)
class LocalLLMConfig:
    ollama_host: str
    model: str
    embed_model: str
    top_k: int
    repo_root: Path
    chroma_path: Path
    chunk_lines: int
    chunk_overlap: int


def load_config(repo_root: Path | None = None) -> LocalLLMConfig:
    root = (repo_root or Path(os.environ.get("LOCAL_LLM_REPO_ROOT", DEFAULT_REPO_ROOT))).resolve()
    chroma_env = os.environ.get("LOCAL_LLM_CHROMA_PATH")
    chroma_path = Path(chroma_env) if chroma_env else root / DEFAULT_CHROMA_REL
    return LocalLLMConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
        model=os.environ.get("LOCAL_LLM_MODEL", DEFAULT_MODEL),
        embed_model=os.environ.get("LOCAL_LLM_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        top_k=int(os.environ.get("LOCAL_LLM_TOP_K", DEFAULT_TOP_K)),
        repo_root=root,
        chroma_path=chroma_path,
        chunk_lines=DEFAULT_CHUNK_LINES,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )
```

- [ ] **Step 4: テストを実行して PASS を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_config.py -v
```

期待: 2 件 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/__init__.py apps/python/src/local_llm/config.py \
        apps/python/tests/local_llm/__init__.py apps/python/tests/local_llm/test_config.py
git commit -m "feat(local-llm): add config module with env overrides"
```

---

## Task 3: `indexer.chunk_file()` と `iter_source_files()`

**Files:**
- Create: `apps/python/src/local_llm/indexer.py`
- Modify: `apps/python/tests/local_llm/test_indexer.py`

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_indexer.py`:

```python
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
```

- [ ] **Step 2: 実行して失敗を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v
```

期待: `ImportError` で FAIL。

- [ ] **Step 3: `indexer.py` の chunk 部分を実装**

`apps/python/src/local_llm/indexer.py`:

```python
"""リポジトリ走査 / chunk / 埋め込み / Chroma upsert。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .config import (
    EXCLUDE_DIRS,
    EXTENSION_ALLOWLIST,
    LocalLLMConfig,
    MAX_FILE_BYTES,
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_path: str
    start_line: int
    end_line: int
    text: str


def iter_source_files(cfg: LocalLLMConfig) -> Iterator[Path]:
    root = cfg.repo_root
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix not in EXTENSION_ALLOWLIST:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def chunk_file(path: Path, cfg: LocalLLMConfig) -> list[Chunk]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return []

    rel = path.relative_to(cfg.repo_root).as_posix()
    step = cfg.chunk_lines - cfg.chunk_overlap
    out: list[Chunk] = []
    i = 0
    while i < len(lines):
        start = i + 1
        end = min(i + cfg.chunk_lines, len(lines))
        body = "\n".join(lines[i:end])
        cid = hashlib.sha256(
            f"{rel}:{start}-{end}:{body}".encode("utf-8")
        ).hexdigest()
        out.append(Chunk(
            chunk_id=cid,
            source_path=rel,
            start_line=start,
            end_line=end,
            text=body,
        ))
        if end >= len(lines):
            break
        i += step
    return out
```

- [ ] **Step 4: テストを実行して PASS を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v
```

期待: 4 件 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/indexer.py apps/python/tests/local_llm/test_indexer.py
git commit -m "feat(local-llm): add file walker and line-based chunker"
```

---

## Task 4: `Indexer` クラス — embed / Chroma upsert / 削除検出

**Files:**
- Modify: `apps/python/src/local_llm/indexer.py`
- Modify: `apps/python/tests/local_llm/test_indexer.py`

- [ ] **Step 1: 失敗するテストを追記**

`apps/python/tests/local_llm/test_indexer.py` の末尾に追記:

```python
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
        return {"ids": list(self.data.keys())}

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
        # 決定論的ダミーベクトル
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
    assert olm2.calls == 0  # hash skip で埋め込み無し


def test_indexer_detects_modified_and_deleted(tmp_path):
    from src.local_llm.indexer import Indexer

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("v1\n")
    b.write_text("hello\n")
    cfg = load_config(repo_root=tmp_path)
    coll = FakeCollection()

    Indexer(cfg, collection=coll, ollama_client=FakeOllama()).run()

    a.write_text("v2\n")  # 内容変更
    b.unlink()             # ファイル削除

    olm = FakeOllama()
    stats = Indexer(cfg, collection=coll, ollama_client=olm).run()
    assert stats.added >= 1  # 新 chunk_id
    assert stats.deleted >= 1  # b.py の chunk が消える

    # b.py が collection に残っていないこと
    remaining = [r["meta"]["source_path"] for r in coll.data.values()]
    assert "b.py" not in remaining
```

- [ ] **Step 2: 実行して失敗を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v
```

期待: `Indexer` 未定義で FAIL。

- [ ] **Step 3: `Indexer` を実装**

`apps/python/src/local_llm/indexer.py` の末尾に追記:

```python
from dataclasses import field
from typing import Protocol


class _OllamaLike(Protocol):
    def embeddings(self, model: str, prompt: str) -> dict: ...


class _CollectionLike(Protocol):
    def get(self, ids=None, where=None, include=None) -> dict: ...
    def upsert(self, ids, embeddings, documents, metadatas) -> None: ...
    def delete(self, ids=None, where=None) -> None: ...


@dataclass
class IndexStats:
    files: int = 0
    chunks: int = 0
    added: int = 0
    updated: int = 0
    deleted: int = 0


class Indexer:
    def __init__(
        self,
        cfg: LocalLLMConfig,
        *,
        collection: _CollectionLike,
        ollama_client: _OllamaLike,
    ) -> None:
        self.cfg = cfg
        self.collection = collection
        self.ollama = ollama_client

    def run(self) -> IndexStats:
        stats = IndexStats()
        seen_files: set[str] = set()
        seen_ids_by_file: dict[str, set[str]] = {}

        for path in iter_source_files(self.cfg):
            chunks = chunk_file(path, self.cfg)
            if not chunks:
                continue
            stats.files += 1
            stats.chunks += len(chunks)

            rel = chunks[0].source_path
            seen_files.add(rel)
            seen_ids_by_file[rel] = {c.chunk_id for c in chunks}

            existing = set(self.collection.get(
                where={"source_path": rel}
            ).get("ids", []))
            new_ids = [c.chunk_id for c in chunks if c.chunk_id not in existing]
            stale_ids = [i for i in existing if i not in seen_ids_by_file[rel]]

            to_embed = [c for c in chunks if c.chunk_id in new_ids]
            if to_embed:
                embeddings = [
                    self.ollama.embeddings(
                        model=self.cfg.embed_model,
                        prompt=c.text,
                    )["embedding"]
                    for c in to_embed
                ]
                self.collection.upsert(
                    ids=[c.chunk_id for c in to_embed],
                    embeddings=embeddings,
                    documents=[c.text for c in to_embed],
                    metadatas=[
                        {
                            "source_path": c.source_path,
                            "start_line": c.start_line,
                            "end_line": c.end_line,
                        }
                        for c in to_embed
                    ],
                )
                if existing:
                    stats.updated += len(to_embed)
                else:
                    stats.added += len(to_embed)

            if stale_ids:
                self.collection.delete(ids=stale_ids)
                stats.deleted += len(stale_ids)

        # ファイルごと削除されたものを検出
        all_existing = self.collection.get().get("ids", [])
        for cid in all_existing:
            meta = self.collection.data.get(cid, {}).get("meta") if hasattr(self.collection, "data") else None
            if meta and meta["source_path"] not in seen_files:
                self.collection.delete(where={"source_path": meta["source_path"]})
                stats.deleted += 1

        return stats
```

注: `self.collection.data` への直接アクセスは FakeCollection の都合。Chroma 本体では `collection.get(include=["metadatas"])` で metadata を取得する必要があるため、Step 5 で実 Chroma 用ヘルパに置き換える。

- [ ] **Step 4: テストを実行**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v
```

期待: 6 件 PASS。

- [ ] **Step 5: ファイル削除検出を Chroma 互換に直す**

Step 3 の末尾ブロックを以下に置き換え:

```python
        all_data = self.collection.get(include=["metadatas"])
        all_ids = all_data.get("ids", [])
        all_metas = all_data.get("metadatas", [])
        deleted_paths: set[str] = set()
        for meta in all_metas:
            sp = meta.get("source_path") if isinstance(meta, dict) else None
            if sp and sp not in seen_files and sp not in deleted_paths:
                self.collection.delete(where={"source_path": sp})
                deleted_paths.add(sp)
        stats.deleted += len(deleted_paths)
```

FakeCollection 側にも `include=["metadatas"]` 対応を追加:

```python
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
```

- [ ] **Step 6: 再度テストを実行**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v
```

期待: 6 件 PASS。

- [ ] **Step 7: Commit**

```bash
git add apps/python/src/local_llm/indexer.py apps/python/tests/local_llm/test_indexer.py
git commit -m "feat(local-llm): add Indexer with content-hash skip and deletion detection"
```

---

## Task 5: `Retriever` — retrieve / build_context_text / generate stream

**Files:**
- Create: `apps/python/src/local_llm/retriever.py`
- Create: `apps/python/tests/local_llm/test_retriever.py`

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_retriever.py`:

```python
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
```

- [ ] **Step 2: 実行して失敗を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_retriever.py -v
```

期待: `ImportError` で FAIL。

- [ ] **Step 3: `retriever.py` を実装**

`apps/python/src/local_llm/retriever.py`:

```python
"""Chroma での top-k 取得と Ollama での生成。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol

from .config import LocalLLMConfig

PROMPT_TEMPLATE = """以下のコード断片だけを根拠に、日本語で質問に答えてください。
断片に書かれていないことは推測せず「分からない」と答えてください。
回答の末尾に Sources: として参照ファイル名を列挙してください。

## Context
{context}

## Question
{question}
"""


@dataclass(frozen=True)
class RetrievedChunk:
    source_path: str
    start_line: int
    end_line: int
    text: str
    distance: float


class _CollectionLike(Protocol):
    def query(self, query_embeddings, n_results) -> dict: ...


class _OllamaLike(Protocol):
    def embeddings(self, model: str, prompt: str) -> dict: ...
    def generate(self, model: str, prompt: str, stream: bool) -> Iterable[dict]: ...


def build_context_text(chunks: Iterable[RetrievedChunk]) -> str:
    parts: list[str] = []
    for c in chunks:
        parts.append(f"[{c.source_path}:{c.start_line}-{c.end_line}]\n{c.text}")
    return "\n---\n".join(parts)


class Retriever:
    def __init__(
        self,
        cfg: LocalLLMConfig,
        *,
        collection: _CollectionLike,
        ollama_client: _OllamaLike,
    ) -> None:
        self.cfg = cfg
        self.collection = collection
        self.ollama = ollama_client

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self.cfg.top_k
        qv = self.ollama.embeddings(model=self.cfg.embed_model, prompt=question)["embedding"]
        res = self.collection.query(query_embeddings=[qv], n_results=k)
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        return [
            RetrievedChunk(
                source_path=m["source_path"],
                start_line=int(m["start_line"]),
                end_line=int(m["end_line"]),
                text=d,
                distance=float(dist),
            )
            for d, m, dist in zip(docs, metas, dists)
        ]

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> Iterator[str]:
        prompt = PROMPT_TEMPLATE.format(
            context=build_context_text(chunks),
            question=question,
        )
        for piece in self.ollama.generate(
            model=self.cfg.model, prompt=prompt, stream=True
        ):
            tok = piece.get("response", "")
            if tok:
                yield tok
            if piece.get("done"):
                break
```

- [ ] **Step 4: テストを実行**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_retriever.py -v
```

期待: 4 件 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/retriever.py apps/python/tests/local_llm/test_retriever.py
git commit -m "feat(local-llm): add Retriever with top-k query and streaming generate"
```

---

## Task 6: ファクトリ — Ollama / Chroma クライアント生成と起動時チェック

**Files:**
- Create: `apps/python/src/local_llm/clients.py`
- Create: `apps/python/tests/local_llm/test_clients.py`

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_clients.py`:

```python
import pytest

from src.local_llm.clients import OllamaUnavailable, ensure_models_available


class StubClient:
    def __init__(self, models):
        self._models = models

    def list(self):
        return {"models": [{"name": m} for m in self._models]}


def test_ensure_models_available_ok():
    ensure_models_available(StubClient(["qwen2.5:7b", "nomic-embed-text"]), "qwen2.5:7b", "nomic-embed-text")


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
```

- [ ] **Step 2: 実行して失敗を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_clients.py -v
```

期待: ImportError で FAIL。

- [ ] **Step 3: `clients.py` を実装**

`apps/python/src/local_llm/clients.py`:

```python
"""Ollama / Chroma クライアントのファクトリと起動時チェック。"""

from __future__ import annotations

from .config import COLLECTION_NAME, LocalLLMConfig


class OllamaUnavailable(RuntimeError):
    pass


def ensure_models_available(client, model: str, embed_model: str) -> None:
    try:
        info = client.list()
    except Exception as e:
        raise OllamaUnavailable(
            "Cannot reach Ollama. Run 'ollama serve' to start it. "
            f"(underlying error: {e})"
        ) from e

    available = {m["name"] for m in info.get("models", [])}
    missing = [m for m in (model, embed_model) if m not in available]
    if missing:
        cmds = "\n  ".join(f"ollama pull {m}" for m in missing)
        raise OllamaUnavailable(
            f"Required models not pulled: {', '.join(missing)}.\n  {cmds}"
        )


def make_ollama_client(cfg: LocalLLMConfig):
    import ollama
    return ollama.Client(host=cfg.ollama_host)


def make_chroma_collection(cfg: LocalLLMConfig):
    import chromadb
    cfg.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(cfg.chroma_path))
    return client.get_or_create_collection(COLLECTION_NAME)
```

- [ ] **Step 4: テストを実行**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_clients.py -v
```

期待: 3 件 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/clients.py apps/python/tests/local_llm/test_clients.py
git commit -m "feat(local-llm): add ollama/chroma client factories and preflight check"
```

---

## Task 7: CLI — argparse, `--status`, `--sources`

**Files:**
- Create: `apps/python/src/local_llm/cli.py`
- Create: `apps/python/src/local_llm/__main__.py`
- Create: `apps/python/tests/local_llm/test_cli.py`

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_cli.py`:

```python
import pytest

from src.local_llm import cli


def test_cli_status_prints_summary(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))

    class FakeColl:
        def count(self):
            return 42

    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg: FakeColl())

    rc = cli.main(["--status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "42" in out
    assert "qwen2.5:7b" in out
    assert "nomic-embed-text" in out


def test_cli_sources_prints_top_k(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))

    from src.local_llm.retriever import RetrievedChunk

    class FakeRetriever:
        def __init__(self, *a, **kw): pass
        def retrieve(self, question, top_k=None):
            return [
                RetrievedChunk(source_path="a.py", start_line=1, end_line=10, text="", distance=0.1),
                RetrievedChunk(source_path="b.md", start_line=4, end_line=8, text="", distance=0.5),
            ]

    monkeypatch.setattr(cli, "Retriever", FakeRetriever)
    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg: object())
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)

    rc = cli.main(["--sources", "認証はどう動く？", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "a.py:1-10" in out
    assert "b.md:4-8" in out


def test_cli_requires_one_action(tmp_path):
    with pytest.raises(SystemExit):
        cli.main([])
```

- [ ] **Step 2: 実行して失敗を確認**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_cli.py -v
```

期待: ImportError で FAIL。

- [ ] **Step 3: `cli.py` と `__main__.py` を実装**

`apps/python/src/local_llm/__main__.py`:

```python
from .cli import main
import sys

sys.exit(main(sys.argv[1:]))
```

`apps/python/src/local_llm/cli.py`:

```python
"""local_llm CLI エントリ。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .clients import (
    OllamaUnavailable,
    ensure_models_available,
    make_chroma_collection,
    make_ollama_client,
)
from .config import load_config
from .indexer import Indexer
from .retriever import Retriever


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m local_llm")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", action="store_true", help="リポジトリを index")
    group.add_argument("--ask", metavar="QUESTION", help="質問に回答（生成あり）")
    group.add_argument("--sources", metavar="QUESTION", help="top-k のファイル位置だけ表示")
    group.add_argument("--status", action="store_true", help="現在の index 統計を表示")
    p.add_argument("--root", type=Path, default=None, help="リポジトリルート override")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--model", default=None, help="生成モデル override")
    p.add_argument("--reset", action="store_true", help="--index 時に .chroma_db を消して全件再構築")
    return p


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_config(repo_root=args.root)
    if args.model:
        cfg = cfg.__class__(**{**cfg.__dict__, "model": args.model})
    if args.top_k:
        cfg = cfg.__class__(**{**cfg.__dict__, "top_k": args.top_k})

    if args.status:
        return _cmd_status(cfg)
    if args.index:
        return _cmd_index(cfg, reset=args.reset)
    if args.sources is not None:
        return _cmd_sources(cfg, args.sources)
    if args.ask is not None:
        return _cmd_ask(cfg, args.ask)
    return 2


def _cmd_status(cfg) -> int:
    coll = make_chroma_collection(cfg)
    count = coll.count() if hasattr(coll, "count") else 0
    print(f"chroma_path : {cfg.chroma_path}")
    print(f"model       : {cfg.model}")
    print(f"embed_model : {cfg.embed_model}")
    print(f"top_k       : {cfg.top_k}")
    print(f"indexed     : {count} chunks")
    return 0


def _cmd_index(cfg, *, reset: bool) -> int:
    if reset and cfg.chroma_path.exists():
        ans = input(f"Delete {cfg.chroma_path}? [y/N]: ").strip().lower()
        if ans != "y":
            print("aborted")
            return 1
        shutil.rmtree(cfg.chroma_path)

    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    coll = make_chroma_collection(cfg)
    import time
    t0 = time.time()
    stats = Indexer(cfg, collection=coll, ollama_client=olm).run()
    dt = time.time() - t0
    print(
        f"indexed {stats.files} files, {stats.chunks} chunks "
        f"(added {stats.added}, updated {stats.updated}, deleted {stats.deleted}) "
        f"in {dt:.1f}s"
    )
    return 0


def _cmd_sources(cfg, question: str) -> int:
    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    coll = make_chroma_collection(cfg)
    chunks = Retriever(cfg, collection=coll, ollama_client=olm).retrieve(question)
    if not chunks:
        print("該当する文脈が見つかりませんでした")
        return 0
    print(f"{'distance':>10}  source")
    for c in chunks:
        print(f"{c.distance:>10.4f}  {c.source_path}:{c.start_line}-{c.end_line}")
    return 0


def _cmd_ask(cfg, question: str) -> int:
    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    coll = make_chroma_collection(cfg)
    retr = Retriever(cfg, collection=coll, ollama_client=olm)
    chunks = retr.retrieve(question)
    if not chunks:
        print("該当する文脈が見つかりませんでした")
        return 0

    for tok in retr.generate(question, chunks):
        print(tok, end="", flush=True)
    print()

    seen = []
    for c in chunks:
        key = f"{c.source_path}:{c.start_line}-{c.end_line}"
        if key not in seen:
            seen.append(key)
    print("\nSources:")
    for s in seen:
        print(f"  - {s}")
    return 0
```

- [ ] **Step 4: テストを実行**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/test_cli.py -v
```

期待: 3 件 PASS。

- [ ] **Step 5: 全テストを実行**

```bash
cd apps/python && .venv/bin/pytest tests/local_llm/ -v
```

期待: 全件 PASS。

- [ ] **Step 6: Commit**

```bash
git add apps/python/src/local_llm/cli.py apps/python/src/local_llm/__main__.py \
        apps/python/tests/local_llm/test_cli.py
git commit -m "feat(local-llm): add CLI with --index/--ask/--sources/--status"
```

---

## Task 8: bin ラッパスクリプト

**Files:**
- Create: `apps/python/bin/local_llm.sh`
- Create: `bin/local_llm.sh`

- [ ] **Step 1: `apps/python/bin/local_llm.sh` を作成**

既存の `apps/python/bin/chat.sh` を参考に同形で作る:

```bash
cat apps/python/bin/chat.sh
```

`apps/python/bin/local_llm.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$APP_DIR"
if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi
exec "$PY" -m local_llm "$@"
```

注: 上記は `chat.sh` の構造を踏襲する想定。実ファイルと差異があれば合わせること。

- [ ] **Step 2: ルートラッパを作成**

`bin/local_llm.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT_DIR/apps/python/bin/local_llm.sh" "$@"
```

- [ ] **Step 3: 実行権限を付与して動作確認**

```bash
chmod +x apps/python/bin/local_llm.sh bin/local_llm.sh
bin/local_llm.sh --help
```

期待: argparse の help が表示される。

- [ ] **Step 4: Commit**

```bash
git add apps/python/bin/local_llm.sh bin/local_llm.sh
git commit -m "feat(local-llm): add bin wrapper scripts"
```

---

## Task 9: README に「Local LLM (experimental)」セクション追加

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 現状の README 末尾を確認**

```bash
tail -40 README.md
```

- [ ] **Step 2: セクションを追記**

`README.md` の適切な位置（既存セクションの末尾、TOC があれば TOC も更新）に追記:

```markdown
## Local LLM (experimental)

Optional fully-local RAG over this repository, powered by Ollama + Chroma.
The existing Claude Code / briefing / XSS agents are unaffected.

### Prerequisites

```bash
brew install ollama       # or follow https://ollama.com
ollama serve &
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```markdown

### Usage

```bash
bin/local_llm.sh --index                 # index ~/work/ai-agent into Chroma
bin/local_llm.sh --status                # show indexed chunk count & models
bin/local_llm.sh --ask "認証はどう動く？"
bin/local_llm.sh --sources "認証はどう動く？"   # retrieval-only debug
bin/local_llm.sh --index --reset         # rebuild from scratch
```text

Chroma data is stored in `apps/python/.chroma_db/` (gitignored).

Override defaults via env: `LOCAL_LLM_MODEL`, `LOCAL_LLM_EMBED_MODEL`,
`LOCAL_LLM_TOP_K`, `LOCAL_LLM_CHROMA_PATH`, `OLLAMA_HOST`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(local-llm): add experimental Local LLM RAG section"
```

---

## Task 10: 実機検証 (受け入れ条件)

実 Ollama 環境での手動検証。テストではカバーできない統合確認。

- [ ] **Step 1: Ollama 起動とモデル取得**

```bash
ollama serve &
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

- [ ] **Step 2: 初回 index**

```bash
bin/local_llm.sh --index
```

期待出力例:
```text
indexed N files, M chunks (added M, updated 0, deleted 0) in T.Ts
```

- [ ] **Step 3: ベースラインクエリ 3 件を実行し結果を保存**

```bash
bin/local_llm.sh --ask "ブリーフィングは何のスケジュールでどう動く？" | tee /tmp/q1.txt
bin/local_llm.sh --ask "Web UI のチャットはどこからジョブを起こす？" | tee /tmp/q2.txt
bin/local_llm.sh --ask "run_claude() の auth_mode 切替の流れは？" | tee /tmp/q3.txt
```

PR 本文に貼り付け、#135-#138 で再利用する。

- [ ] **Step 4: 2 回目の index で skip 動作を確認**

```bash
bin/local_llm.sh --index
```

期待: `added 0, updated 0` を含む出力。

- [ ] **Step 5: `--status` で件数確認**

```bash
bin/local_llm.sh --status
```

期待: chunks > 0, model/embed_model が既定値。

- [ ] **Step 6: PR を作成**

```bash
git push -u origin feature/issue-140-local-llm-bootstrap
gh pr create --base dev --title "feat(local-llm): bootstrap Ollama+Chroma RAG CLI (#140)" --body "$(cat <<'EOF'
## Summary
- Add `apps/python/src/local_llm/` (config/indexer/retriever/clients/cli) with `python -m local_llm` entry
- Add `bin/local_llm.sh` wrapper and README section
- Tracks Issue #140 (Epic #139); follow-up issues #135-#138 will layer on top

## Baseline queries (for #135-#138 before/after)
1. ブリーフィングは何のスケジュールでどう動く？
   <貼り付け>
2. Web UI のチャットはどこからジョブを起こす？
   <貼り付け>
3. run_claude() の auth_mode 切替の流れは？
   <貼り付け>

## Test plan
- [x] `pytest tests/local_llm/ -v` 全 PASS
- [x] `--index` がローカル Ollama で完走
- [x] `--ask` が回答 + Sources を返す
- [x] 2 回目の `--index` が `added 0` で skip
- [x] `--status` が件数・モデル名を表示

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review notes

- 全タスクが spec の各セクションをカバー: config (T2) / 走査・chunk (T3) / Indexer + 削除検出 (T4) / Retriever (T5) / クライアントと preflight (T6) / CLI (T7) / bin (T8) / README (T9) / 受け入れ条件 (T10)。
- `chunk_id` の決定方法は spec 修正版に合わせ Task 3 で実装、Task 4 で skip ロジックが id 一致で動く。
- 型名・関数名は全 Task で一致 (`Chunk`, `RetrievedChunk`, `Indexer`, `Retriever`, `LocalLLMConfig`, `load_config`, `ensure_models_available`, `make_chroma_collection`, `make_ollama_client`).
- placeholder なし。各 step に実コード or 実コマンドを置いた。
