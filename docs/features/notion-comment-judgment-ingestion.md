# Notion コメント → judgment learning loop 取り込み (#396)

Notion のブリーフィングページに残された人間のコメントを、`judge` 学習ループ (`judgments.jsonl`) のイベントへ変換する。既存の `judge` CLI（`~/work/dotfiles-claude/bin/judge`）を経由するため、スキーマ・ID採番ロジックはそちらに一元化されている。設計背景: `docs/reports/system-audit-2026-07-17.md` §7-4、`~/work/dotfiles-claude/docs/learning-loop-design.md`。

## 仕組み

`weekly_handler.py`（週次バッチ）の末尾で以下を実行する。ベストエフォート — 失敗しても週次サマリー自体は成功として返す。

1. `judgment_ingest.judge_available()` — `~/work/dotfiles-claude/bin/judge` が存在しなければ即スキップ。
2. `notifier.notion.fetch_commentable_pages()` — briefing データベース内の `agent` タグ付きページのうち、直近7日で**編集**されたもの（`created_time` ではなく `last_edited_time` 基準。古いページへの新規コメントも拾える）。
3. `notion_comment_state.read_seen_ids()` — 取り込み済みコメントIDを `~/.ai-agent/ingested_notion_comments.json` から読み込む。
4. `notifier.notion.fetch_new_comments()` — 対象ページの未取り込みコメントを取得（空文字コメントは除外）。
5. 各コメントを `judgment_ingest.record_comment_as_judgment()` で `judge note --domain brief-gen --reason "<コメント原文>" --context "..."` として記録。
6. 成功したコメントIDのみ `notion_comment_state.write_seen_ids()` で永続化（失敗したものは次回リトライ対象として残す）。

## 設計上の決定

- **verdict は一律 `note`**: Notion コメントは既に配信済みブリーフィングへの事後コメントであり、取引上の「却下」には当たらない。reject/revise の分類は行わず、`reason` にコメント原文をそのまま保存する。人間が判断ルールへ蒸留する段階（`judgment-distill`）で分類すればよい、という割り切り。
- **judge CLI を subprocess 起動**（jsonl 直接追記ではない）: ID採番・スキーマの単一情報源を `judge` 側に保つため。`~/work/<repo>` 前提のパス解決は `local_llm/config.py` の `DEFAULT_REPO_ROOT` と同じ既存規約に倣っている。
- **dedup 状態は ai-agent 側で保持**: `~/.ai-agent/ingested_notion_comments.json`（`state.json` と同じアトミック書き込みパターン）。judge 側の `judgments.jsonl` は追記専用でコメントIDを持たないため、逆引きできない。

## 動作要件

- `judge` CLI が `~/work/dotfiles-claude/bin/judge` に存在すること（なければ静かにスキップ、エラーにはならない）。
- `NOTION_API_KEY` / `NOTION_DATABASE_ID` が設定済みで、ページへの comments 読み取り権限（integration の capabilities で "Read comments" 有効化）があること。
