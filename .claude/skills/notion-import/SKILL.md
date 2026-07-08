---
name: notion-import
description: Use when the user wants to save the previous research/answer to a local markdown file and append it to today's Notion briefing page
argument-hint: "<topic-slug>"
allowed-tools: Write, mcp__claude_ai_Notion__notion-search, mcp__claude_ai_Notion__notion-update-page
---

# Notion Import

会話の直前の調査結果・回答内容を、ローカル md ファイルに保存しつつ、今日の Notion ブリーフィングページ末尾に追記する。

## Usage

```
/notion-import <topic-slug>
```

- `<topic-slug>` はファイル名用の kebab-case 識別子（例: `distyl-ai-ipo-check`, `tsmc-2nm-update`）
- 追記する内容は **直前の assistant 回答** を正本とする（ユーザーから別途指定がなければ）

## 動作ポリシー（確認なし・自動追記）

- **事前確認は一切しない。** 追記の可否やトピック slug、内容を聞き返さず、直前の回答をそのまま正本として即座に追記する。
- slug が未指定なら、直前の回答内容から自動で kebab-case の slug を生成する。
- 追記する本文を改めてチャットに再掲しない（やりとりを省く）。完了報告だけを 1〜2 行で返す。

## Workflow

### 1. ローカル md ファイル作成

パス: `output/<topic-slug>_<YYYY-MM-DD>.md`

- 日付は今日（`MEMORY.md` の `currentDate` または `date +%F` で確認）
- セクション構成（推奨テンプレート）:
  ```markdown
  # <タイトル> (<YYYY-MM-DD>)

  ## 結論
  <1〜2文の要点>

  ## <セクション>
  <本文・表・箇条書き>

  ## ソース
  - [<タイトル>](<URL>)
  ```
- ソース URL は会話中に WebSearch などで得たものだけを使用（捏造しない）

### 2. 今日の Notion ブリーフィングページを特定

`mcp__claude_ai_Notion__notion-search` で以下を検索:

- クエリ: `マーケットブリーフィング YYYY-MM-DD`（今日の日付）
- `page_size: 5`, `max_highlight_length: 0`
- タイトルが `マーケットブリーフィング — YYYY-MM-DD` に一致するページの `id` を取得

ヒットしない場合は、その旨をユーザーに報告して停止（勝手に別のページに書き込まない）。

### 3. ページ末尾に追記

`mcp__claude_ai_Notion__notion-update-page` を以下で呼ぶ:

- `command: insert_content`
- `position: {"type": "end"}`
- `content`: 区切り線 + 見出しから始める

content の冒頭テンプレート:

```markdown
---

## 追記: <タイトル> (<YYYY-MM-DD>)

<本文>
```

本文はステップ1で書いた md と同等の内容（先頭の `# <タイトル>` は重複するので削る）。

### 4. 完了報告

ユーザーに 1〜2 行で（本文の再掲はしない）:
- 保存した md パス
- Notion ページの URL（`https://www.notion.so/<id-without-dashes>`）

## Notes

- **直前の回答が長い場合**: 全文ではなく要約版を作るのではなく、構造を保ったまま転記する（ユーザーが「いい感じ」と評価した形式を維持）
- **ローカル md と Notion 本文の差分**: ローカル md には `# トップタイトル` を残し、Notion 側は `## 追記:` 見出しから始める（ブリーフィング本文との階層整合のため）
- **複数追記**: 同じ日に2回以上呼ばれた場合も、毎回 `---` + `## 追記:` で末尾に積む
- **失敗時のフォールバック**: Notion 検索が失敗してもローカル md は既に保存済みなので、ユーザーには「ローカルは保存済み、Notion 追記は失敗」と明示
