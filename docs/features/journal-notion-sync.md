# Journal ↔ Notion 連携仕様（ドラフト）

## 目的

Web の Journal 機能で起票・追記した内容を、Notion の Journal 専用データベース（`NOTION_DATABASE_ID_JOURNAL`）にも同期する。

- 新規起票 → Notion に新規ページ作成
- 同じエントリへの追記 → 同じ Notion ページに追記（新規ページを増やさない）

## 現状（調査結果）

- ローカル Journal はすべて完結しており、Notion 送信は未実装。
  - `apps/python/src/journal_store.py`: 1 entry = 1 ファイル（`output/journal/{entry_id}.md`）。`append_entry` / `append_to_entry` などを提供。
  - `apps/python/web/routers/journal.py`: `POST /api/journal`（新規作成）、`PATCH /api/journal/{entry_id}`（追記）。
- Notion 送信の既存実装は briefing 用の `apps/python/src/notifier/notion.py`。
  - `send_to_notion()`（L42-114）: `databases.retrieve` でタイトルプロパティ名を解決 → `notion.pages.create` → 100 blocks 超は `blocks.children.append` で分割追加。
  - 「既存ページに追記」のロジックはコード側になく、`.claude/skills/notion-import/SKILL.md` がスキル層で `notion-search` → 該当ページに `insert_content` する形で代替している。
- `NOTION_DATABASE_ID_JOURNAL` は `apps/python/src/credentials.py` の `ALLOWED_KEYS`（L22）に**追加済み**だが、`.env.example` への記載および `config.py` での読み出しは未実装。

## 設計方針

### 1. Notion ページと Journal entry の対応付け

`journal_store` の各エントリ（`entry_id`）に対して、対応する Notion `page_id` を保持する必要がある。

- エントリの frontmatter または metadata に `notion_page_id` を追加し、初回同期時に書き込む。
- 2回目以降の追記はこの `notion_page_id` を使い、`notion-search` のような曖昧検索に頼らず直接 `blocks.children.append` する。

### 2. 新規起票時（`POST /api/journal`）

1. ローカルにエントリ作成（既存動作）。
2. `NOTION_DATABASE_ID_JOURNAL` に対して `notion.pages.create()` で新規ページ作成（`send_to_notion` 相当のロジックを再利用 or 抽出して共通化）。
3. 返ってきた `page_id` をエントリの metadata に保存。
4. Notion 側書き込みが失敗してもローカル作成自体は成功させる（同期は best-effort、失敗はログのみ）。

### 3. 追記時（`PATCH /api/journal/{entry_id}`）

1. ローカルに追記（既存動作）。
2. エントリ metadata から `notion_page_id` を取得。
   - 存在すれば `notion.blocks.children.append(page_id, children=[...])` で追記ブロックを末尾追加。
   - 存在しない場合（過去分など同期前のエントリ）は新規作成にフォールバックし、`notion_page_id` を新たに保存。

### 4. 設定まわりの変更点

- `.env.example` に `NOTION_DATABASE_ID_JOURNAL=your_notion_journal_database_id_here` を追記。
- `apps/python/src/config.py` に Journal 用データベース ID を読む口を追加（既存の `notion_database_id` パターンに倣う）。
- `apps/python/config/briefing.json.example` / `apps/python/tests/config/briefing.json` にスキーマ追加が必要な場合は両方更新（CLAUDE.md のルール通り）。

## 未確定事項（要確認）

- Notion 側のタイトルプロパティ値: エントリの日付 or 先頭行タイトルのどちらを使うか。
- 1日1ページ（date 単位でまとめる）か、1 entry = 1 ページか。「同じエントリなら追記」という要件なので後者（1 entry = 1 page）を前提にした。
- Notion 送信失敗時のリトライ方針（現状 briefing 側もリトライなしの best-effort）。
