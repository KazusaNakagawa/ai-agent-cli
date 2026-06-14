# Local-LLM Briefing Path — Design Spec

Date: 2026-06-08
Issue: [#142](https://github.com/KazusaNakagawa/ai-agent-cli/issues/142)
Depends on: #140 (merged in `cffec7a`)

Parallel briefing path that uses the local Ollama stack from #140 instead of Claude, and pushes the output to Notion via the existing `notifier/notion.py`. Run alongside the current Claude-backed briefing so quality and cost can be compared without disturbing the production schedule.

## Goal

Make `bin/local_llm.sh --briefing` produce a daily briefing from the same `BriefingConfig` (portfolio / themes / geopolitical / watch_events) using qwen2.5:7b, save the markdown to `apps/python/output/briefing/local_<YYYY-MM-DD>.md`, and optionally post it to Notion via `--notion`.

## 非ゴール

- Web 取得（外部検索）の追加 — 別 Issue。ローカル版は **WebSearch を使わない**。caveat を本文先頭に明記する。
- 既存 Claude ブリーフィングへの変更（プロンプト・スケジュール・出力先すべて触らない）
- Discord 配信（Notion のみ。重複通知防止）
- セクタースイープ（並列）の再現 — メイン分析 1 本に絞る
- weekly_handler / XSS / Web UI への波及

## アーキテクチャ

### 新規 / 変更ファイル

```text
apps/python/src/local_llm/
  briefing.py                 # NEW: プロンプト組立 → ollama.generate → markdown
  cli.py                      # MOD: --briefing / --notion フラグ追加
apps/python/prompts/
  local_briefing.md           # NEW: 既存 briefing.md から WebSearch 指示を除去
apps/python/tests/local_llm/
  test_briefing.py            # NEW: prompt 組立とフォーマット検証
README.md                     # MOD: Local LLM セクションに --briefing を追記
```

### コンポーネント分離

| ユニット | 責務 | 依存 |
|---|---|---|
| `local_llm.briefing.build_local_briefing_prompt(cfg, stocks)` | BriefingConfig + 株価データ → プロンプト文字列 | `generator.briefing._build_*_context` の関数を `from src.generator.briefing import ...` で再利用 |
| `local_llm.briefing.generate_local_briefing(prompt, ollama, model)` | Ollama 呼び出し（stream → 1 本のテキストに集約） | `clients.make_ollama_client` |
| `local_llm.briefing.compose_briefing_md(body, model, generated_at)` | caveat ヘッダ + 本文の組成 | なし |
| `cli._cmd_briefing(cfg, *, post_to_notion)` | 上記を順に呼んでファイル保存と Notion 投稿を行う | `fetch_stock_moves`, `notifier.notion.send_to_notion` |

各ユニットは pure 関数で副作用を最小化し、テスト時に Ollama / Notion を inject / stub できる構造を維持する。

### プロンプト

`apps/python/prompts/local_briefing.md` は `briefing.md` のコピーから以下を変更:

1. 先頭の "WebSearchを使って今日の最新情報を調べたうえで、" を削除
2. 「## 調査すること」セクションを「## 入力情報」に改題し、「下記のデータと、あなたが既に知っている範囲の知識だけを根拠に分析してください。確認できない最新情報は推測しないでください」を追記
3. 出力フォーマット部分（### 今日のサマリー〜### 参考記事）はそのまま。ただし「### 参考記事」は WebSearch がないので末尾に「（モデル知識ベースなので URL は省略可）」を補記
4. 既存の `$themes` `$tickers` `$geopolitical` `$watch_events` `$stocks` 変数は同じく `string.Template.substitute()` 互換のまま

`generator.prompt.render()` をそのまま使えるように、テンプレートディレクトリと拡張子の規約に従う。

### ヘッダ caveat

`compose_briefing_md()` が貼る固定 caveat（本文先頭、生成本文の前）:

```text
> **※ ローカル LLM 生成（実験版）**
> - model: qwen2.5:7b （`LOCAL_LLM_MODEL` で上書き可能）
> - WebSearch 未使用 — モデルの学習知識と入力データのみで生成
> - generated_at: 2026-06-08T...
> - 比較先: 同日 Claude 版は `briefing_2026-06-08.md`

---
```

## データフロー

1. CLI が `--briefing` を受け取る
2. `src.config.load_config()` で `BriefingConfig` を読む（既存実装）
3. `fetch_stock_moves(cfg.portfolio.tickers)` で前日比文字列を取得（既存）
4. `build_local_briefing_prompt(cfg, stocks)` でプロンプト生成
5. `generate_local_briefing()` で Ollama に投げ、stdout にトークンをストリーミングしつつ全文を蓄積
6. `compose_briefing_md()` で caveat + 本文を結合
7. `apps/python/output/briefing/local_<YYYY-MM-DD>.md` に書き出し
8. `--notion` 指定時のみ `send_to_notion(md, NOTION_API_KEY, NOTION_DATABASE_ID, title="ローカルブリーフィング — <date>", tags=["agent", "local"])`

## CLI

```text
bin/local_llm.sh --briefing [--notion] [--model qwen2.5:7b] [--root PATH]
```

- `--briefing` は他のアクション（`--index`/`--ask`/`--sources`/`--status`）と相互排他
- `--notion` は単独では無効（`--briefing` と組み合わせ必須）
- 既存の `--model` / `--root` はそのまま流用

## エラーハンドリング（境界のみ）

| 失敗ケース | 挙動 |
|---|---|
| Ollama 未起動 / モデル未 pull | `clients.ensure_models_available` が raise → stderr に案内 → exit 1 |
| `BriefingConfig` ロード失敗 | `src.config.load_config()` が raise → そのまま伝播（briefing.json 未配置の operator 失敗） |
| `fetch_stock_moves` 失敗 | exit 1 として CLI 終了。caveat に "stock fetch failed" を入れる |
| 出力 dir 作成失敗 | OSError をそのまま raise（CLI なので traceback で十分） |
| Notion 投稿失敗 | `send_to_notion` が空文字 URL を返す。stderr に警告のみ。MD は既に保存済み |

## テスト

`apps/python/tests/local_llm/test_briefing.py`:

| テスト | 内容 |
|---|---|
| `test_build_local_briefing_prompt_renders_template` | tmp fixture の minimal BriefingConfig → プロンプトに各セクションのキーワードが含まれること |
| `test_compose_briefing_md_includes_caveat_header` | caveat と本文が `---` で区切られ、model 名と generated_at が入る |
| `test_generate_local_briefing_collects_stream_tokens` | FakeOllama（chunked yield）→ 全文を 1 本に結合 |
| `test_cmd_briefing_writes_local_file_and_skips_notion_by_default` | 出力ファイルが `output/briefing/local_<date>.md` に作られ、Notion mock は呼ばれない |
| `test_cmd_briefing_posts_to_notion_when_flag_set` | `--notion` 指定で Notion mock が 1 回呼ばれる |

Ollama / Notion / yfinance 呼び出しは全て monkeypatch で stub。

## 受け入れ条件 (Issue #142 準拠)

- [ ] `bin/local_llm.sh --briefing` がローカル Ollama でブリーフィングを生成し `local_<date>.md` を作成
- [ ] caveat ヘッダに model 名と「WebSearch 未使用」の文言が含まれる
- [ ] `--notion` フラグで Notion に投稿（手動検証で 1 件確認）
- [ ] 既存の `bin/briefing.py` フロー / Claude 版出力 / launchd スケジュールに無変更
- [ ] PR 本文に同日の Claude 版 vs ローカル版の冒頭抜粋を貼る
