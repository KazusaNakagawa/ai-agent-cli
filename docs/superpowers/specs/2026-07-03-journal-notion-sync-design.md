# Journal ↔ Notion 連携 設計

## 目的

Web の Journal 機能で起票・追記した内容を、Notion の Journal 専用データベース（`NOTION_DATABASE_ID_JOURNAL`）に同期する。

- 新規起票 → Notion に新規ページ作成
- 同じエントリへの追記 → 同じ Notion ページに追記（新規ページを増やさない）

## 前提（調査結果）

- `apps/python/src/journal_store.py`: 1 entry = 1 ファイル（`output/journal/{entry_id}.md`）。`save_item`/`get_item` が `{entry_id}.json` サイドカーに短いラベルを保存している。
- `apps/python/web/routers/journal.py`: `POST /api/journal`（新規作成）、`PATCH /api/journal/{entry_id}`（追記）。
- `apps/python/src/notifier/notion.py` の `send_to_notion()`（L42-114）が既存の Notion ページ作成ロジック（タイトルプロパティ解決 → `notion.pages.create` → 100 blocks 超は `blocks.children.append` で分割）を持つ。
- `NOTION_DATABASE_ID_JOURNAL` は `apps/python/src/credentials.py` の `ALLOWED_KEYS` に追加済み（現在の差分）。`.env.example` 記載・`config.py` 読み出しは未実装。

## 設計方針

### 1. Notion ページと Journal entry の対応付け

`journal_store.py` の `{entry_id}.json` サイドカーを拡張し、`notion_page_id` を保持する。

- 既存: `{"item": "<label>"}`
- 拡張後: `{"item": "<label>", "notion_page_id": "<id>"}`
- 新規ヘルパーを追加: `save_notion_meta(entry_id, page_id)` / `get_notion_meta(entry_id)`。既存の `save_item`/`get_item` と同じファイルを読み書きするため、キーの欠落を許容してマージする。

### 2. タイトル生成

Notion ページタイトルはエントリ本文の先頭行から生成する。

1. 本文の先頭行を取得する。
2. 先頭の見出し・リスト記号（`#`, `-`, `*` など）を除去し、前後の空白をトリムする。
3. 結果が空文字なら、エントリの日付（`YYYY-MM-DD`）にフォールバックする。
4. 60 文字を超える場合は 60 文字で切り詰める。

このロジックは `journal_store.py` 内に純粋関数として実装し、単体でテストする。

### 3. 新規起票時（`POST /api/journal`）

1. ローカルにエントリ作成（既存動作）。
2. `NOTION_DATABASE_ID_JOURNAL` が設定されていれば、Notion 同期を同期的に呼び出す（`sync_journal_entry()` など、`send_to_notion()` のロジックを再利用する薄いラッパーを新設）。
3. 成功時: 返ってきた `page_id` を `save_notion_meta()` で保存する。
4. Notion 側書き込みが失敗してもローカル作成自体は成功させる（best-effort、失敗はログのみ、API レスポンスには影響しない）。

### 4. 追記時（`PATCH /api/journal/{entry_id}`）

1. ローカルに追記（既存動作）。
2. `get_notion_meta(entry_id)` で `notion_page_id` を取得する。
   - 存在すれば `notion.blocks.children.append(page_id, children=[...])` で追記ブロックを末尾追加する。
   - 存在しない場合（過去分など同期前のエントリ）は新規作成にフォールバックし、`notion_page_id` を新たに保存する。
3. 失敗時はログのみ、API レスポンスは成功のまま返す。

### 5. ページ単位

1 entry = 1 Notion ページとする（1 日に複数エントリがあれば複数ページになる）。「同じエントリなら追記」という要件に自然に一致する。

### 6. 同期タイミング

Notion 同期は API リクエストのハンドラ内で同期的に実行する（バックグラウンドタスク化はしない）。実装がシンプルであることを優先し、Notion 側の遅延は許容する。

### 7. 設定まわりの変更点

- `.env.example` に `NOTION_DATABASE_ID_JOURNAL=your_notion_journal_database_id_here` を追記。
- `apps/python/src/config.py` に Journal 用データベース ID を読む口を追加（既存の `notion_database_id` パターンに倣う）。
- `apps/python/config/briefing.json.example` / `apps/python/tests/config/briefing.json` にスキーマ追加が必要な場合は両方更新する（CLAUDE.md のルール通り）。
- `apps/python/src/credentials.py` の `ALLOWED_KEYS` への `NOTION_DATABASE_ID_JOURNAL` 追加（現在の差分）はそのまま活かす。

## テスト方針

- `notion_client.Client` をモックしたユニットテストを追加する。
  - 新規作成成功時に `notion_page_id` が保存されること。
  - `notion_page_id` がある場合に追記が `blocks.children.append` を呼ぶこと。
  - `notion_page_id` がない場合に新規作成へフォールバックすること。
  - Notion 呼び出し失敗時もローカル操作自体は成功として返ること（best-effort）。
  - タイトル整形ロジック（記号除去・切り詰め・空フォールバック）の単体テスト。

## 未確定事項（残なし）

ドラフト時点の未確定事項（タイトル方針、ページ単位、リトライ方針）はいずれもこの設計で確定した。リトライは実施しない（既存 `send_to_notion` と同じく best-effort・リトライなし）。
