# Obsidian 連携設計（ジャーナル片方向同期 + vault チャット RAG）

日付: 2026-07-17
ステータス: 承認済みドラフト

## 目的

ローカルの Obsidian vault（ただの Markdown フォルダ）と ai-agent を 2 点で連携する:

1. **ジャーナル → vault 片方向同期**: Web ジャーナルの起票・追記を vault 内のファイルへ書き出す（Notion 同期と並ぶ第2の同期先）。
2. **vault → チャット RAG**: vault 全体のノートを専用 Chroma コレクションに索引し、チャット回答時に関連ノートをコンテキスト注入する（#395 クロス日付ブリーフィング RAG と同型）。

方式は **ローカルファイル直接読み書き**。Obsidian アプリ・プラグイン・REST API・MCP コネクタには依存しない。vault はローカルフォルダなので、書き込んだ .md は Obsidian が自動で拾う。

## スコープ外

- 双方向同期（vault 側の編集をジャーナルへ取り込むこと）
- ブリーフィング生成時の vault 参照
- vault → Notion など他系統への転送

## 設定

`briefing.json` に `obsidian` セクションを追加（省略可。未設定なら全機能が no-op）:

```json
"obsidian": {
  "vault_path": "/Users/xxx/Documents/MyVault",
  "journal_subdir": "journal",
  "exclude_dirs": [".obsidian", ".trash", "templates"]
}
```

- `src/config.py`: `ObsidianConfig(BaseModel)` を新設し `BriefingConfig` に `obsidian: ObsidianConfig | None = None` として追加。
- `exclude_dirs` の既定値は `[".obsidian", ".trash", "templates"]`。`journal_subdir` の既定値は `"journal"`。
- CLAUDE.md のルール通り `config/briefing.json.example` と `tests/config/briefing.json` を両方更新（tests 側は tmp を指すダミーパスではなく、未設定 = None のままにしてテスト内で明示注入する）。

## コンポーネント 1: ジャーナル → vault 同期

### 新規モジュール `src/notifier/obsidian_sync.py`

- `sync_entry(entry_id: str, vault_path: Path, journal_subdir: str) -> None`
  - `journal_store` からエントリ全文を読み、`<vault>/<journal_subdir>/<entry_id>.md` へ**全文上書き**で書き出す。
  - 追記差分の管理はしない（ローカルの entry ファイルが常に正で、毎回全文コピー）。Notion 同期のような page_id 対応管理が不要になる。
  - 書き出し先ディレクトリは `mkdir(parents=True, exist_ok=True)`。

### フック（`web/routers/journal.py`）

- 既存の Notion 同期タスク（`_sync_new_entry_task` / `_sync_append_task`）と並べて、`background_tasks.add_task` で vault 同期タスクを追加。
- best-effort: `obsidian` 設定が None なら即 return、書き込み失敗は `logger.exception` のみでローカル操作・Notion 同期には影響させない。
- 対象エンドポイント: 新規起票（POST）と追記（PATCH）の両方。削除・trash は同期しない（スコープ外、vault 側に残る）。

## コンポーネント 2: vault → チャット RAG

### 新規モジュール `src/local_llm/obsidian_index.py`

`briefing_index.py` と同型の薄いラッパー:

- `OBSIDIAN_COLLECTION_NAME = "obsidian-notes"` を `local_llm/config.py` に追加。
- `index_obsidian(cfg, *, vault_path) -> IndexStats`: `dataclasses.replace(cfg, repo_root=vault_path)` で Indexer を vault に向け、専用コレクションへ増分索引。
- `retrieve_obsidian_context(cfg, question, *, top_k, vault_path) -> list[RetrievedChunk]`: `ensure_models_available` で embed モデル存在確認後に top-k 取得（briefing 側と同じく `OllamaUnavailable` を前置で送出）。
- **除外ディレクトリ**: Indexer が `exclude_dirs` 配下をスキップできることが前提。既存 Indexer にディレクトリ除外機構がなければ、`LocalLLMConfig` に除外リストを追加して Indexer の走査でフィルタする（briefing 索引には影響しない形で）。

### CLI（`src/local_llm/cli.py`）

- `--index-obsidian` フラグを `--index-briefings` と対で追加。`--reset` 併用で全件再構築。
- vault 未設定時は設定を促すエラーメッセージを出して終了コード非0。

### チャット統合（`web/routers/chat.py`）

- 既存の `retrieve_briefing_context` 呼び出しと並べて `retrieve_obsidian_context` を呼び、取得チャンクを `build_context_text` でまとめる。
- `chat_session.build_cmd` に `vault_context: str | None` を追加し、`wrap_untrusted(..., label="obsidian_note_excerpts")` で履歴ブリーフィング抜粋と同様に注入。出典ファイル名（vault 相対パス）の明記を指示文に含める。
- vault 未設定・コレクション未構築・Ollama 停止時は briefing RAG と同じ degrade（注入なしで回答継続、ログのみ）。

## エラー処理方針（共通）

- vault パスが存在しない: 起動時チェックはせず、使用時（同期・索引・検索）に警告ログを出して no-op / エラー終了（CLI のみ非0）。
- すべての同期・検索は best-effort。ジャーナル本体・チャット本体の成功可否に影響させない。

## テスト計画

- `tests/test_obsidian_sync.py`: `tmp_path` を vault に見立て、(a) 起票同期でファイルが生成される、(b) 追記後の再同期で全文が上書きされる、(c) 設定 None で no-op、(d) 書き込み失敗（読み取り専用ディレクトリ等）でも例外が漏れない。
- `tests/test_obsidian_index.py`: (a) `exclude_dirs` 配下の .md が索引対象外になる、(b) `repo_root` が vault に差し替わったコレクションに書かれる（briefing 側テストのパターン踏襲、Ollama/Chroma はフェイク）。
- ルーターテスト: journal POST/PATCH で vault 同期タスクが登録されること（Notion 同期テストのパターン踏襲）。

## 決定事項の記録

| 論点 | 決定 |
|---|---|
| 連携方式 | ローカルファイル直接読み書き（REST API プラグイン・MCP は不採用） |
| ジャーナル同期方向 | 片方向（ジャーナル → vault）、全文上書き |
| RAG の用途 | チャット回答時のコンテキスト注入のみ |
| 索引範囲 | vault 全体（除外リストで `.obsidian` 等を除く） |
| 失敗時挙動 | best-effort、本体処理に影響させない |
