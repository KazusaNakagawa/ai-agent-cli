# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## セットアップ・実行

```bash
# 仮想環境作成・依存インストール
uv venv .venv
uv pip sync requirements.txt

# 実行（ブリーフィング + XSS Intel を連続実行）
bin/run.sh

# 単体実行
source .venv/bin/activate
python bin/briefing.py
python bin/xss_intel.py
```

## 依存パッケージ管理

`requirements.in` が直接依存の手動管理ファイル。`requirements.txt` は自動生成なので直接編集しない。

```bash
# パッケージ追加後
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
```

## アーキテクチャ

2つのエージェントが独立して動作する。共通の Discord/Notion notifier を共有。

### ブリーフィングエージェント

```
bin/briefing.py
  └── src/handler.py
        ├── src/fetcher/stocks.py        # yfinance で portfolio.tickers の前日比を取得
        ├── src/generator/briefing.py    # claude CLI を subprocess で呼び出し
        │     └── prompts/briefing.md    # {tickers}{themes}{geopolitical}{watch_sectors}{stocks} を埋め込む
        ├── src/notifier/discord.py
        └── src/notifier/notion.py
```

### XSS Intel エージェント

```
bin/xss_intel.py
  └── src/xss_handler.py
        ├── src/generator/xss_report.py  # claude CLI を subprocess で呼び出し
        │     └── prompts/xss_intel.md
        ├── src/notifier/discord.py
        └── src/notifier/notion.py
```

### 設定スキーマ（`src/config.py`）

- `BriefingConfig` — `PortfolioConfig` + `GeopoliticalConfig` + `list[WatchSector]` を保持
- `XssIntelConfig` — `XssTargetsConfig`（frameworks/libraries/keywords）を保持
- `CONFIG = load_config()` はモジュールロード時に実行される（モジュールレベルシングルトン）
- `get_xss_config()` は初回アクセス時のみ読み込むレイジーシングルトン

### 設定ファイル（`config/`）

- `briefing.json` — `portfolio`（tickers/themes）・`watch_sectors`（14セクター）・`geopolitical.conflicts` を管理。コードを触らずに監視対象を変更できる
- `xss_intel.json` — `targets`（frameworks/libraries/keywords）を管理

### プロンプトテンプレート（`prompts/`）

`src/generator/prompt.py` の `render()` が `prompts/{name}.md` を `str.format(**kwargs)` で展開する。プロンプトを変更する場合は `.md` ファイルのみ編集する。

### Claude CLI の呼び出し方

`subprocess.run(["claude", "-p", prompt, "--allowedTools", "WebSearch"])` でWebSearch付きで呼び出す。タイムアウトは300秒。

## 環境変数（`.env`）

| 変数名 | 用途 |
|---|---|
| `DISCORD_TOKEN` | Discord Bot 認証 |
| `CHANNEL_ID` | Discord 送信先チャンネル |
| `NOTION_API_KEY` | Notion API 認証 |
| `NOTION_DATABASE_ID` | Notion 送信先データベース |

## ログ

`log/{YYYYMMDD}-app.log` に DEBUG レベルで出力。コンソールは INFO レベル。`src/logger.py` の `get_logger()` で取得する。
