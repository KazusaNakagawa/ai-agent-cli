# Obsidian 連携 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obsidian vault へのジャーナル片方向同期と、vault ノートをチャット RAG のコンテキストとして注入する機能を追加する。

**Architecture:** vault はローカル Markdown フォルダなので、同期はファイル全文上書き（`src/notifier/obsidian_sync.py`）、RAG は既存 `briefing_index.py` と同型の薄いラッパー（`src/local_llm/obsidian_index.py`）＋専用 Chroma コレクションで実現。設定は `briefing.json` の省略可能な `obsidian` セクション。未設定なら全機能 no-op。

**Tech Stack:** Python 3.13 / Pydantic v2 / FastAPI / ChromaDB / Ollama（既存依存のみ、追加なし）

**Spec:** `docs/superpowers/specs/2026-07-17-obsidian-integration-design.md`

## Global Constraints

- コード内コメント・docstring は英語（CLAUDE.md）。
- テスト実行はすべて `apps/python/` から `.venv/bin/pytest`。
- config スキーマ変更時は `config/briefing.json.example` を更新。`tests/config/briefing.json` は `obsidian` 未設定のまま（optional フィールドのため valid。テストでの有効化は monkeypatch で行う — spec の決定事項）。
- すべての同期・検索は best-effort。ジャーナル本体・チャット本体の成功可否に影響させない。
- コミットは Conventional Commits 形式（`feat:` / `test:` など、英語サマリー）。

---

### Task 1: ObsidianConfig（設定スキーマ）

**Files:**
- Modify: `apps/python/src/config.py`
- Modify: `apps/python/config/briefing.json.example`
- Test: `apps/python/tests/test_config.py`

**Interfaces:**
- Produces: `src.config.ObsidianConfig`（Pydantic model: `vault_path: str`, `journal_subdir: str = "journal"`, `exclude_dirs: list[str]`）
- Produces: `src.config.get_obsidian_config() -> ObsidianConfig | None` — briefing.json が無い / 読めない / `obsidian` 未設定なら None。後続タスク（journal router / chat router / CLI）はすべてこの関数で設定を取得する。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/test_config.py` の末尾に追記:

```python
def test_obsidian_config_parsed_when_present(tmp_path, monkeypatch):
    raw = json.loads((Path("tests/config/briefing.json")).read_text(encoding="utf-8"))
    raw["obsidian"] = {"vault_path": "/tmp/vault"}
    cfg_file = tmp_path / "briefing.json"
    cfg_file.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_file)

    loaded = config.load_config()
    assert loaded.obsidian is not None
    assert loaded.obsidian.vault_path == "/tmp/vault"
    # Defaults
    assert loaded.obsidian.journal_subdir == "journal"
    assert loaded.obsidian.exclude_dirs == [".obsidian", ".trash", "templates"]


def test_obsidian_config_none_when_absent(tmp_path, monkeypatch):
    # tests/config/briefing.json has no obsidian section
    loaded = config.load_config()
    assert loaded.obsidian is None
    assert config.get_obsidian_config() is None


def test_get_obsidian_config_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "missing.json")
    assert config.get_obsidian_config() is None
```

既存 import を確認し、`import json` / `from pathlib import Path` / `from src import config` が無ければ追加（既存テストのスタイルに合わせる。既存が `from src.config import load_config` 等の直 import なら合わせて書き換え可、ただし `monkeypatch.setattr(config, "CONFIG_PATH", ...)` はモジュール属性への setattr なので `src.config` モジュール自体を import すること）。

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_config.py -v -k obsidian`
Expected: FAIL（`obsidian` attribute が存在しない / `get_obsidian_config` 未定義）

- [ ] **Step 3: 実装**

`apps/python/src/config.py` — `BriefingFileConfig` の直前に追加:

```python
class ObsidianConfig(BaseModel):
    """Optional Obsidian vault integration settings (journal sync + chat RAG)."""

    model_config = ConfigDict(extra="forbid")

    vault_path: str
    journal_subdir: str = "journal"
    exclude_dirs: list[str] = Field(
        default_factory=lambda: [".obsidian", ".trash", "templates"]
    )
```

`BriefingFileConfig` にフィールド追加（`watch_events` の下）:

```python
    # Optional Obsidian vault integration (#TBD-issue). None = feature disabled.
    obsidian: ObsidianConfig | None = None
```

`get_journal_notion_credentials()` の下に追加:

```python
def get_obsidian_config() -> ObsidianConfig | None:
    """Return the ``obsidian`` section of briefing.json, or None when disabled.

    Best-effort by design: a missing briefing.json, a validation error, or an
    absent ``obsidian`` section all mean "feature off" — callers (journal sync,
    chat RAG, CLI) must not fail because of Obsidian configuration.
    """
    try:
        return load_config().obsidian
    except Exception:
        return None
```

`apps/python/config/briefing.json.example` に追記（トップレベルキーとして。JSON なのでコメント不可、既存スタイルに従い値で示す）:

```json
  "obsidian": {
    "vault_path": "/Users/yourname/Documents/MyVault",
    "journal_subdir": "journal",
    "exclude_dirs": [".obsidian", ".trash", "templates"]
  }
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_config.py -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/config.py apps/python/config/briefing.json.example apps/python/tests/test_config.py
git commit -m "feat: add optional obsidian section to briefing config"
```

---

### Task 2: obsidian_sync モジュール（ジャーナル → vault 書き出し）

**Files:**
- Create: `apps/python/src/notifier/obsidian_sync.py`
- Test: `apps/python/tests/test_obsidian_sync.py`

**Interfaces:**
- Consumes: `journal_store.read_entry(entry_id) -> str | None`（既存）
- Produces: `src.notifier.obsidian_sync.sync_entry(entry_id: str, vault_path: Path, journal_subdir: str) -> None` — エントリ全文を `<vault>/<journal_subdir>/<entry_id>.md` に上書き書き出し。vault 不存在・エントリ不存在は警告ログのみで return（例外を投げない）。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/test_obsidian_sync.py` を新規作成:

```python
"""Tests for journal -> Obsidian vault one-way sync.

Contract:
- ``sync_entry`` writes the entry's full content to
  ``<vault>/<journal_subdir>/<entry_id>.md`` (overwrite, not append).
- Missing vault dir or missing entry logs and returns without raising.
"""
from unittest.mock import patch

from src.notifier import obsidian_sync


def test_sync_entry_writes_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="# Note\nbody"):
        obsidian_sync.sync_entry("2026-07-17_120000", vault, "journal")
    dest = vault / "journal" / "2026-07-17_120000.md"
    assert dest.read_text(encoding="utf-8") == "# Note\nbody"


def test_sync_entry_overwrites_on_resync(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="v1"):
        obsidian_sync.sync_entry("2026-07-17_120000", vault, "journal")
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="v1\nv2"):
        obsidian_sync.sync_entry("2026-07-17_120000", vault, "journal")
    dest = vault / "journal" / "2026-07-17_120000.md"
    assert dest.read_text(encoding="utf-8") == "v1\nv2"


def test_sync_entry_noop_when_vault_missing(tmp_path):
    missing = tmp_path / "no-such-vault"
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value="body"):
        obsidian_sync.sync_entry("2026-07-17_120000", missing, "journal")  # must not raise
    assert not missing.exists()


def test_sync_entry_noop_when_entry_missing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with patch.object(obsidian_sync.journal_store, "read_entry", return_value=None):
        obsidian_sync.sync_entry("2026-07-17_999999", vault, "journal")  # must not raise
    assert not (vault / "journal").exists()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_obsidian_sync.py -v`
Expected: FAIL（`ModuleNotFoundError: src.notifier.obsidian_sync`）

- [ ] **Step 3: 実装**

`apps/python/src/notifier/obsidian_sync.py` を新規作成:

```python
"""Journal -> Obsidian vault one-way sync (best-effort).

An Obsidian vault is a plain folder of Markdown files, so syncing an entry
means writing its full current content to
``<vault>/<journal_subdir>/<entry_id>.md``. The local journal entry is the
source of truth: every sync overwrites the vault copy, so no incremental /
append bookkeeping (like the Notion page-id mapping) is needed.
"""
from pathlib import Path

from src import journal_store
from src.logger import get_logger

logger = get_logger(__name__)


def sync_entry(entry_id: str, vault_path: Path, journal_subdir: str) -> None:
    """Write the entry's full content into the vault, overwriting any copy.

    Never raises for expected failure modes (missing vault, missing entry):
    this runs as a best-effort background task and must not disturb the
    caller. Unexpected I/O errors propagate to the caller's guard.
    """
    content = journal_store.read_entry(entry_id)
    if content is None:
        logger.warning("obsidian sync skipped: journal entry not found: %s", entry_id)
        return
    if not vault_path.is_dir():
        logger.warning("obsidian sync skipped: vault path does not exist: %s", vault_path)
        return
    dest_dir = vault_path / journal_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / f"{entry_id}.md").write_text(content, encoding="utf-8")
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_obsidian_sync.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/notifier/obsidian_sync.py apps/python/tests/test_obsidian_sync.py
git commit -m "feat: add journal-to-obsidian vault sync module"
```

---

### Task 3: journal ルーターへの同期フック

**Files:**
- Modify: `apps/python/web/routers/journal.py`
- Test: `apps/python/tests/test_api_journal.py`

**Interfaces:**
- Consumes: `config.get_obsidian_config()`（Task 1）、`obsidian_sync.sync_entry(entry_id, vault_path, journal_subdir)`（Task 2）
- Produces: POST `/api/journal` と PATCH `/api/journal/{entry_id}` が Notion 同期タスクに加えて Obsidian 同期タスクを background_tasks に登録する。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/test_api_journal.py` の末尾に追記（既存の `from unittest.mock import patch` を利用）:

```python
async def test_append_syncs_to_obsidian_vault(authed_client, journal_dir, tmp_path, monkeypatch):
    from src.config import ObsidianConfig
    from web.routers import journal as journal_router

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(
        journal_router.config, "get_obsidian_config",
        lambda: ObsidianConfig(vault_path=str(vault)),
    )
    response = await authed_client.post(
        "/api/journal", json={"content": "obsidian sync test", "date": "2026-07-17"}
    )
    assert response.status_code == 200
    entry_id = response.json()["id"]
    dest = vault / "journal" / f"{entry_id}.md"
    assert dest.exists()
    assert "obsidian sync test" in dest.read_text(encoding="utf-8")


async def test_patch_resyncs_full_content_to_obsidian(authed_client, journal_dir, tmp_path, monkeypatch):
    from src.config import ObsidianConfig
    from web.routers import journal as journal_router

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(
        journal_router.config, "get_obsidian_config",
        lambda: ObsidianConfig(vault_path=str(vault)),
    )
    created = await authed_client.post(
        "/api/journal", json={"content": "first", "date": "2026-07-17"}
    )
    entry_id = created.json()["id"]
    response = await authed_client.patch(
        f"/api/journal/{entry_id}", json={"content": "second"}
    )
    assert response.status_code == 204
    text = (vault / "journal" / f"{entry_id}.md").read_text(encoding="utf-8")
    assert "first" in text and "second" in text


async def test_append_succeeds_when_obsidian_sync_raises(authed_client, journal_dir, monkeypatch):
    from web.routers import journal as journal_router

    def _boom():
        raise RuntimeError("config exploded")

    monkeypatch.setattr(journal_router.config, "get_obsidian_config", _boom)
    response = await authed_client.post(
        "/api/journal", json={"content": "still works", "date": "2026-07-17"}
    )
    assert response.status_code == 200
```

注意: `monkeypatch.setattr(journal_router.config, ...)` は `src.config` モジュールの属性を差し替える（journal.py は `from src import config` 形式のため）。他テストへの影響は monkeypatch が自動で戻す。

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_api_journal.py -v -k obsidian`
Expected: FAIL（vault にファイルが生成されない）

- [ ] **Step 3: 実装**

`apps/python/web/routers/journal.py`:

import に追加:

```python
from src.notifier import journal_sync, obsidian_sync
```

（既存の `from src.notifier import journal_sync` を書き換え。`from pathlib import Path` は既存 import 済み。）

`_sync_append_task` の下に追加:

```python
def _sync_obsidian_task(entry_id: str) -> None:
    """Best-effort background sync of the entry's full content into the vault."""
    try:
        obsidian = config.get_obsidian_config()
        if obsidian:
            obsidian_sync.sync_entry(
                entry_id, Path(obsidian.vault_path).expanduser(), obsidian.journal_subdir
            )
    except Exception:
        logger.exception("Obsidian journal sync failed for entry %s", entry_id)
```

`append_journal`（POST）の `background_tasks.add_task(_sync_new_entry_task, ...)` の直後に:

```python
    background_tasks.add_task(_sync_obsidian_task, entry_id)
```

`patch_journal`（PATCH）の `background_tasks.add_task(_sync_append_task, ...)` の直後に:

```python
    background_tasks.add_task(_sync_obsidian_task, entry_id)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_api_journal.py -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/web/routers/journal.py apps/python/tests/test_api_journal.py
git commit -m "feat: sync journal entries to obsidian vault on create and append"
```

---

### Task 4: Indexer のディレクトリ除外拡張

**Files:**
- Modify: `apps/python/src/local_llm/config.py`
- Modify: `apps/python/src/local_llm/indexer.py`
- Test: `apps/python/tests/local_llm/test_indexer.py`

**Interfaces:**
- Produces: `LocalLLMConfig.extra_exclude_dirs: frozenset[str] = frozenset()` — 既存の `EXCLUDE_DIRS` に**追加**で適用されるディレクトリ名集合。既定は空なので既存の索引挙動（repo / briefing）は不変。
- Produces: `iter_source_files` が `EXCLUDE_DIRS | cfg.extra_exclude_dirs` でフィルタする。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_indexer.py` に追記（既存テストの cfg 生成ヘルパーがあればそれを使う。無ければ以下の形で直接 `LocalLLMConfig` を構築する — 既存テストの構築方法を必ず確認して合わせること）:

```python
def test_iter_source_files_respects_extra_exclude_dirs(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "keep.md").write_text("keep", encoding="utf-8")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "daily.md").write_text("tmpl", encoding="utf-8")

    cfg = _make_cfg(tmp_path, extra_exclude_dirs=frozenset({".obsidian", "templates"}))
    rels = sorted(p.relative_to(tmp_path).as_posix() for p in iter_source_files(cfg))
    assert rels == ["notes/keep.md"]


def test_iter_source_files_default_excludes_unchanged(tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    cfg = _make_cfg(tmp_path)  # extra_exclude_dirs defaults to empty
    rels = [p.relative_to(tmp_path).as_posix() for p in iter_source_files(cfg)]
    assert rels == ["a.md"]
```

`_make_cfg` は既存テストのコンフィグ生成に合わせる。既存に無い場合の定義:

```python
def _make_cfg(root, **overrides):
    from src.local_llm.config import LocalLLMConfig
    base = dict(
        ollama_host="http://localhost:11434", model="m", synthesis_model="m",
        embed_model="e", num_ctx=1024, temperature=0.0, top_k=3,
        repo_root=root, chroma_path=root / ".chroma_db",
        chunk_lines=40, chunk_overlap=8,
    )
    base.update(overrides)
    return LocalLLMConfig(**base)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v -k exclude`
Expected: FAIL（`extra_exclude_dirs` が未定義で TypeError、または `.obsidian/app.json`（.json は allowlist 内）と `templates/daily.md` が結果に混入）

- [ ] **Step 3: 実装**

`apps/python/src/local_llm/config.py` — `LocalLLMConfig` に既定値付きフィールドを末尾追加:

```python
@dataclass(frozen=True)
class LocalLLMConfig:
    ollama_host: str
    model: str
    synthesis_model: str
    embed_model: str
    num_ctx: int
    temperature: float
    top_k: int
    repo_root: Path
    chroma_path: Path
    chunk_lines: int
    chunk_overlap: int
    # Extra directory names excluded on top of EXCLUDE_DIRS. Lets a caller
    # (e.g. the Obsidian vault indexer) skip vault-internal folders without
    # changing the global exclusion set. Empty = existing behavior.
    extra_exclude_dirs: frozenset[str] = frozenset()
```

`load_config()` は変更不要（既定値のため）。

`apps/python/src/local_llm/indexer.py` — `iter_source_files` を変更:

```python
def iter_source_files(cfg: LocalLLMConfig) -> Iterator[Path]:
    root = cfg.repo_root
    exclude = EXCLUDE_DIRS | cfg.extra_exclude_dirs
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in exclude for part in path.relative_to(root).parts):
            continue
        if path.suffix not in EXTENSION_ALLOWLIST:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/local_llm/test_indexer.py -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/config.py apps/python/src/local_llm/indexer.py apps/python/tests/local_llm/test_indexer.py
git commit -m "feat: support per-config extra exclude dirs in local_llm indexer"
```

---

### Task 5: obsidian_index モジュール（vault 索引・検索）

**Files:**
- Modify: `apps/python/src/local_llm/config.py`（コレクション名定数）
- Create: `apps/python/src/local_llm/obsidian_index.py`
- Test: `apps/python/tests/local_llm/test_obsidian_index.py`

**Interfaces:**
- Consumes: `LocalLLMConfig.extra_exclude_dirs`（Task 4）、既存 `Indexer` / `Retriever` / `make_chroma_collection` / `make_ollama_client` / `ensure_models_available`
- Produces: `OBSIDIAN_COLLECTION_NAME = "obsidian-notes"`（`local_llm/config.py`）
- Produces: `index_obsidian(cfg, *, vault_path: Path, exclude_dirs: list[str]) -> IndexStats`
- Produces: `retrieve_obsidian_context(cfg, question: str, *, top_k: int | None = None, vault_path: Path, exclude_dirs: list[str]) -> list[RetrievedChunk]` — embed モデル未 pull 時は `OllamaUnavailable` を送出（briefing 側と同じ前置チェック）。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_obsidian_index.py` を新規作成。`tests/local_llm/test_briefing_index.py` の `FakeCollection` / `FakeOllama` / `collections` fixture パターンをそのまま踏襲する（fixture 側の monkeypatch 対象を `obsidian_index` モジュールに変えるだけ）。必須テストケース:

```python
def test_index_obsidian_indexes_vault_not_repo_root(tmp_path, collections):
    # vault に notes/a.md を置き、cfg.repo_root は別ディレクトリを指す。
    # index_obsidian(cfg, vault_path=vault, exclude_dirs=[]) 後、
    # "obsidian-notes" コレクションに vault のファイルだけが入ること。
    ...


def test_index_obsidian_skips_exclude_dirs(tmp_path, collections):
    # vault/.obsidian/app.json と vault/templates/t.md と vault/notes/keep.md を作成。
    # exclude_dirs=[".obsidian", ".trash", "templates"] で索引後、
    # コレクションの source_path が "notes/keep.md" のみであること。
    ...


def test_retrieve_obsidian_context_queries_obsidian_collection_only(tmp_path, collections):
    # briefing_index テストの同名ケースと同型: 索引後に retrieve して
    # 返る chunk の source_path が vault のファイルであること。
    ...


def test_retrieve_obsidian_context_raises_ollama_unavailable_when_embed_model_missing(tmp_path, monkeypatch):
    # FakeOllama(pulled_models=()) で retrieve_obsidian_context が
    # OllamaUnavailable を送出すること（briefing_index テストの同名ケースと同型）。
    ...
```

各 `...` は test_briefing_index.py の対応テストの本体を `obsidian_index` 用に書き換えて埋める（コピーして関数名・引数を差し替える。`vault_path` / `exclude_dirs` はキーワード引数）。

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/local_llm/test_obsidian_index.py -v`
Expected: FAIL（`ModuleNotFoundError: src.local_llm.obsidian_index`）

- [ ] **Step 3: 実装**

`apps/python/src/local_llm/config.py` — `BRIEFING_COLLECTION_NAME` の下に追加:

```python
# Separate collection for Obsidian vault RAG so vault notes don't mix with
# repo-code or briefing search results in the same Chroma store.
OBSIDIAN_COLLECTION_NAME = "obsidian-notes"
```

`apps/python/src/local_llm/obsidian_index.py` を新規作成:

```python
"""Index and retrieve Obsidian vault notes for chat RAG.

Same pattern as ``briefing_index``: point ``LocalLLMConfig.repo_root`` at the
vault directory and use a dedicated Chroma collection. The vault's internal
folders (``.obsidian/``, templates, trash) are excluded via
``LocalLLMConfig.extra_exclude_dirs`` so they never get indexed.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from .clients import ensure_models_available, make_chroma_collection, make_ollama_client
from .config import OBSIDIAN_COLLECTION_NAME, LocalLLMConfig
from .indexer import Indexer, IndexStats
from .retriever import RetrievedChunk, Retriever


def _vault_cfg(cfg: LocalLLMConfig, vault_path: Path, exclude_dirs: list[str]) -> LocalLLMConfig:
    return dataclasses.replace(
        cfg, repo_root=vault_path, extra_exclude_dirs=frozenset(exclude_dirs)
    )


def index_obsidian(
    cfg: LocalLLMConfig, *, vault_path: Path, exclude_dirs: list[str]
) -> IndexStats:
    """Incrementally index vault Markdown into the obsidian collection."""
    vcfg = _vault_cfg(cfg, vault_path, exclude_dirs)
    olm = make_ollama_client(vcfg)
    coll = make_chroma_collection(vcfg, collection_name=OBSIDIAN_COLLECTION_NAME)
    return Indexer(vcfg, collection=coll, ollama_client=olm).run()


def retrieve_obsidian_context(
    cfg: LocalLLMConfig,
    question: str,
    *,
    top_k: int | None = None,
    vault_path: Path,
    exclude_dirs: list[str],
) -> list[RetrievedChunk]:
    """Top-k retrieval over indexed vault notes for ``question``.

    Raises ``OllamaUnavailable`` up front (via ``ensure_models_available``)
    if ``embed_model`` isn't pulled, mirroring ``retrieve_briefing_context``.
    """
    vcfg = _vault_cfg(cfg, vault_path, exclude_dirs)
    olm = make_ollama_client(vcfg)
    ensure_models_available(olm, vcfg.embed_model, embed_model=None)
    coll = make_chroma_collection(vcfg, collection_name=OBSIDIAN_COLLECTION_NAME)
    return Retriever(vcfg, collection=coll, ollama_client=olm).retrieve(question, top_k=top_k)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/local_llm/ -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/config.py apps/python/src/local_llm/obsidian_index.py apps/python/tests/local_llm/test_obsidian_index.py
git commit -m "feat: add obsidian vault indexing and retrieval for chat RAG"
```

---

### Task 6: CLI `--index-obsidian`

**Files:**
- Modify: `apps/python/src/local_llm/cli.py`
- Test: `apps/python/tests/local_llm/test_cli.py`

**Interfaces:**
- Consumes: `get_obsidian_config()`（Task 1）、`index_obsidian` / `OBSIDIAN_COLLECTION_NAME`（Task 5）、既存 `delete_collection` / `ensure_models_available` / `make_ollama_client`
- Produces: `python -m local_llm --index-obsidian [--reset]` — vault 未設定/不存在なら stderr にエラーを出し exit 1。`--reset` は `obsidian-notes` コレクションのみ削除（確認プロンプトあり、`_cmd_index_briefings` と同型）。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/local_llm/test_cli.py` に追記（既存テストの main() 呼び出し・monkeypatch パターンを踏襲）:

```python
def test_index_obsidian_errors_when_vault_unconfigured(monkeypatch, capsys):
    from src.local_llm import cli

    monkeypatch.setattr(cli, "get_obsidian_config", lambda: None)
    rc = cli.main(["--index-obsidian"])
    assert rc == 1
    assert "obsidian" in capsys.readouterr().err.lower()


def test_index_obsidian_errors_when_vault_dir_missing(monkeypatch, capsys, tmp_path):
    from src.config import ObsidianConfig
    from src.local_llm import cli

    monkeypatch.setattr(
        cli, "get_obsidian_config",
        lambda: ObsidianConfig(vault_path=str(tmp_path / "no-such-dir")),
    )
    rc = cli.main(["--index-obsidian"])
    assert rc == 1
    assert "vault" in capsys.readouterr().err.lower()


def test_index_obsidian_runs_indexer_on_vault(monkeypatch, capsys, tmp_path):
    from src.config import ObsidianConfig
    from src.local_llm import cli
    from src.local_llm.indexer import IndexStats

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(
        cli, "get_obsidian_config", lambda: ObsidianConfig(vault_path=str(vault))
    )
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda olm, m, e: None)
    captured: dict = {}

    def _fake_index_obsidian(cfg, *, vault_path, exclude_dirs):
        captured["vault_path"] = vault_path
        captured["exclude_dirs"] = exclude_dirs
        return IndexStats(files=1, chunks=2, added=2)

    monkeypatch.setattr(cli, "index_obsidian", _fake_index_obsidian)
    rc = cli.main(["--index-obsidian"])
    assert rc == 0
    assert captured["vault_path"] == vault
    assert captured["exclude_dirs"] == [".obsidian", ".trash", "templates"]
    assert "indexed 1 files" in capsys.readouterr().out
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/local_llm/test_cli.py -v -k obsidian`
Expected: FAIL（`--index-obsidian` が未定義で argparse error → SystemExit）

- [ ] **Step 3: 実装**

`apps/python/src/local_llm/cli.py`:

import に追加:

```python
from src.config import get_obsidian_config
from .config import BRIEFING_COLLECTION_NAME, OBSIDIAN_COLLECTION_NAME, load_config
from .obsidian_index import index_obsidian
```

（既存の `from .config import BRIEFING_COLLECTION_NAME, load_config` 行を書き換え。）

`_build_parser()` の mutually exclusive group に追加（`--index-briefings` の下）:

```python
    group.add_argument("--index-obsidian", action="store_true", help="Obsidian vault を index（チャット RAG 用）")
```

`main()` のディスパッチに追加（`args.index_briefings` の下）:

```python
    if args.index_obsidian:
        return _cmd_index_obsidian(cfg, reset=args.reset)
```

`_cmd_index_briefings` の下に追加:

```python
def _cmd_index_obsidian(cfg, *, reset: bool) -> int:
    """Index the configured Obsidian vault into its dedicated collection.

    Mirrors ``_cmd_index_briefings``: shares ``cfg.chroma_path`` with the
    other collections but must not mix documents or --reset them.
    """
    obsidian = get_obsidian_config()
    if obsidian is None:
        print(
            "Error: obsidian.vault_path is not configured in briefing.json",
            file=sys.stderr,
        )
        return 1
    vault = Path(obsidian.vault_path).expanduser()
    if not vault.is_dir():
        print(f"Error: vault path does not exist: {vault}", file=sys.stderr)
        return 1

    if reset:
        ans = input(f"Delete '{OBSIDIAN_COLLECTION_NAME}' collection at {cfg.chroma_path}? [y/N]: ").strip().lower()
        if ans != "y":
            print("aborted")
            return 1
        delete_collection(cfg, OBSIDIAN_COLLECTION_NAME)

    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
    except (OllamaUnavailable, EmbedModelMismatch) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    t0 = time.time()
    stats = index_obsidian(cfg, vault_path=vault, exclude_dirs=obsidian.exclude_dirs)
    dt = time.time() - t0
    print(
        f"indexed {stats.files} files, {stats.chunks} chunks "
        f"(added {stats.added}, updated {stats.updated}, deleted {stats.deleted}) "
        f"in {dt:.1f}s"
    )
    return 0
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/local_llm/test_cli.py -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/local_llm/cli.py apps/python/tests/local_llm/test_cli.py
git commit -m "feat: add --index-obsidian CLI command"
```

---

### Task 7: chat_session への vault_context 注入

**Files:**
- Modify: `apps/python/src/chat_session.py`
- Test: `apps/python/tests/test_chat_session.py`

**Interfaces:**
- Produces: `build_cmd(target_date, briefing_file, session_file, history_context=None, vault_context=None) -> list[str]` — `vault_context` は新規セッション作成時のみ system prompt に注入（resume 時は無視、history_context と同じ扱い）。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/test_chat_session.py` に追記（既存の build_cmd テストのフィクスチャ／briefing_file 生成パターンを踏襲）:

```python
def test_build_cmd_injects_vault_context_on_new_session(tmp_path):
    briefing_file = tmp_path / "briefing_2026-07-17.md"
    briefing_file.write_text("# briefing", encoding="utf-8")
    session_file = tmp_path / "sessions" / "2026-07-17"

    cmd = build_cmd(
        "2026-07-17", briefing_file, session_file,
        vault_context="[notes/idea.md:1-10]\nvault excerpt",
    )
    prompt = cmd[cmd.index("--append-system-prompt") + 1]
    assert "Obsidian ノートの関連抜粋" in prompt
    assert "vault excerpt" in prompt
    assert "obsidian_note_excerpts" in prompt  # wrap_untrusted label


def test_build_cmd_ignores_vault_context_on_resume(tmp_path):
    briefing_file = tmp_path / "briefing_2026-07-17.md"
    briefing_file.write_text("# briefing", encoding="utf-8")
    session_file = tmp_path / "sessions" / "2026-07-17"
    session_file.parent.mkdir(parents=True)
    session_file.write_text("11111111-1111-1111-1111-111111111111")

    cmd = build_cmd(
        "2026-07-17", briefing_file, session_file, vault_context="excerpt"
    )
    assert "--append-system-prompt" not in cmd
    assert "--resume" in cmd
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_chat_session.py -v -k vault`
Expected: FAIL（`vault_context` 引数が未定義で TypeError）

- [ ] **Step 3: 実装**

`apps/python/src/chat_session.py` — `build_cmd` のシグネチャと docstring を変更し、`history_context` ブロックの直後に注入部を追加:

```python
def build_cmd(
    target_date: str,
    briefing_file: Path,
    session_file: Path,
    history_context: str | None = None,
    vault_context: str | None = None,
) -> list[str]:
```

docstring 末尾に追記:

```python
    ``vault_context`` is retrieved excerpts from the user's Obsidian vault
    notes, injected the same way as ``history_context`` (new sessions only).
```

`if history_context:` ブロックの直後に追加:

```python
    if vault_context:
        context += (
            "\n\n以下はユーザーの Obsidian ノートから検索された関連抜粋です。"
            "各抜粋は冒頭に `[ファイル名:行範囲]` の形式で出典を示しています。"
            "回答内でこれらの抜粋の内容に触れる際は、"
            "対応するファイル名を括弧書きで明記してください。\n\n"
            "=== Obsidian ノートの関連抜粋 ===\n"
            f"{wrap_untrusted(vault_context, label='obsidian_note_excerpts')}\n"
            "=== END ==="
        )
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_chat_session.py -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/python/src/chat_session.py apps/python/tests/test_chat_session.py
git commit -m "feat: inject obsidian vault excerpts into chat session prompt"
```

---

### Task 8: chat ルーターでの vault 検索の配線

**Files:**
- Modify: `apps/python/web/routers/chat.py`
- Test: `apps/python/tests/test_api_chat.py`

**Interfaces:**
- Consumes: `config.get_obsidian_config()`（Task 1）、`retrieve_obsidian_context`（Task 5）、`build_cmd(..., vault_context=...)`（Task 7）、既存 `build_context_text`
- Produces: `POST /api/chat` は obsidian 設定があるとき常に vault 検索を試み、取得抜粋を新規セッションの system prompt に注入する。検索失敗（Ollama 停止・コレクション未構築等）は警告ログのみで回答継続（briefing RAG の 503 とは異なり soft degrade — spec の決定事項）。

- [ ] **Step 1: 失敗するテストを書く**

`apps/python/tests/test_api_chat.py` に追記（既存テストの authed_client / briefing ファイル fixture・subprocess モックのパターンを必ず確認して踏襲。以下は骨子）:

```python
async def test_chat_injects_vault_context_when_obsidian_configured(
    authed_client, tmp_path, monkeypatch, ...  # 既存 fixture に合わせる
):
    from src.config import ObsidianConfig
    from src.local_llm.retriever import RetrievedChunk
    from web.routers import chat as chat_router

    monkeypatch.setattr(
        chat_router.config, "get_obsidian_config",
        lambda: ObsidianConfig(vault_path=str(tmp_path)),
    )
    monkeypatch.setattr(
        chat_router, "retrieve_obsidian_context",
        lambda cfg, q, **kw: [
            RetrievedChunk("notes/idea.md", 1, 5, "vault text", 0.1)
        ],
    )
    # 既存テストと同様に claude subprocess をモックし、POST /api/chat を実行。
    # 生成された cmd の --append-system-prompt に "vault text" と
    # "obsidian_note_excerpts" が含まれることを assert する。


async def test_chat_continues_when_vault_retrieval_fails(
    authed_client, tmp_path, monkeypatch, ...
):
    from src.config import ObsidianConfig
    from web.routers import chat as chat_router

    monkeypatch.setattr(
        chat_router.config, "get_obsidian_config",
        lambda: ObsidianConfig(vault_path=str(tmp_path)),
    )

    def _boom(cfg, q, **kw):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(chat_router, "retrieve_obsidian_context", _boom)
    # POST /api/chat が 202 を返すこと（500 にならないこと）を assert する。


async def test_chat_skips_vault_retrieval_when_unconfigured(
    authed_client, monkeypatch, ...
):
    from web.routers import chat as chat_router

    monkeypatch.setattr(chat_router.config, "get_obsidian_config", lambda: None)
    called = []
    monkeypatch.setattr(
        chat_router, "retrieve_obsidian_context",
        lambda *a, **kw: called.append(1),
    )
    # POST /api/chat 実行後、called == [] を assert する。
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_api_chat.py -v -k vault`
Expected: FAIL（`chat_router` に `retrieve_obsidian_context` / `config` 属性が無い、または prompt に vault text が入らない）

- [ ] **Step 3: 実装**

`apps/python/web/routers/chat.py`:

import に追加（既存 import 群に合わせて）:

```python
from pathlib import Path

from src import config
from src.local_llm.obsidian_index import retrieve_obsidian_context
```

（`Path` / `config` が既に import 済みならそのまま使う。）

`post_chat` の `history_context` ブロックの直後（`SESSIONS_DIR.mkdir` の前）に追加:

```python
    vault_context: str | None = None
    obsidian = config.get_obsidian_config()
    if obsidian:
        # Soft degrade by design: vault RAG is an enhancement, so any failure
        # (Ollama down, collection not built yet) logs and continues without
        # vault context — unlike search_history's explicit 503 contract.
        try:
            vault_chunks = retrieve_obsidian_context(
                load_local_llm_config(),
                body.question,
                vault_path=Path(obsidian.vault_path).expanduser(),
                exclude_dirs=obsidian.exclude_dirs,
            )
            if vault_chunks:
                vault_context = build_context_text(vault_chunks)
        except Exception:
            logger.warning(
                "obsidian vault retrieval failed — continuing without vault context",
                exc_info=True,
            )
```

`build_cmd` の 2 呼び出し箇所（image あり／なし）をともに変更:

```python
        cmd = [*build_cmd(body.date, briefing_file, session_file, history_context, vault_context), "-p", *IMAGE_INPUT_FLAGS, *CHAT_STREAM_FLAGS]
```

```python
        cmd = [*build_cmd(body.date, briefing_file, session_file, history_context, vault_context), "-p", body.question, *CHAT_STREAM_FLAGS]
```

`logger` が chat.py に未定義なら既存パターンで追加:

```python
from src.logger import get_logger

logger = get_logger(__name__)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd apps/python && .venv/bin/pytest tests/test_api_chat.py -v`
Expected: 既存含め全 PASS

- [ ] **Step 5: 全テスト実行**

Run: `cd apps/python && .venv/bin/pytest -q`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add apps/python/web/routers/chat.py apps/python/tests/test_api_chat.py
git commit -m "feat: wire obsidian vault retrieval into chat endpoint"
```
