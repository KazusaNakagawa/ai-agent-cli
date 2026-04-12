# My World Briefing — パーソナル世界情勢エージェント

毎朝、地政学・株式市場・注目テーマを自動収集し、**自分のポートフォリオへの影響**と**なぜそれが起きたか（ストーリー）**を3分で読める形にまとめてDiscordに届けるエージェント。

---

## コンセプト

> 「情報を出すツール」ではなく「自分の文脈に引き寄せて解釈するエージェント」

NewsPicks・Bloombergは情報を出すだけ。このエージェントは保有銘柄・関心テーマ・地政学リスクに紐づけて「自分への示唆」まで生成する点が異なる。

---

## アーキテクチャ

```bash
main.py
  └── src/handler.py
        ├── src/stocks.py       ── yfinance（株価取得）
        ├── src/briefing.py     ── Claude Code CLI（WebSearch）
        │     └── src/prompt.py ── prompts/briefing.md（テンプレート）
        └── src/discord.py      ── Discord Bot API（通知配信）

設定
  config/briefing.json          ── 銘柄・テーマ・地政学リスク
  src/config.py                 ── JSON読み込み + dataclassスキーマ
```

### 特徴
- **NewsAPI不要** — Claude Code CLI の WebSearch ツールがリアルタイム検索
- **Anthropic APIキー不要（ローカル実行時）** — Claude Code CLIの認証を利用
- **地政学リスクと株式の因果関係**を毎日の出力に織り込み

---

## ディレクトリ構成

```bash
ai-agent/
  main.py                 # エントリーポイント
  src/
    handler.py            # オーケストレーション
    briefing.py           # ブリーフィング生成（Claude CLI呼び出し）
    stocks.py             # 株価取得（yfinance）
    discord.py            # Discord送信
    config.py             # 設定スキーマ（dataclass）
    prompt.py             # プロンプトテンプレートレンダラー
    logger.py             # ロガー設定
  config/
    briefing.json         # ユーザー設定（銘柄・テーマ・地政学）
  prompts/
    briefing.md           # プロンプトテンプレート
  log/
    YYYYMMDD-app.log      # 実行ログ（自動生成）
  requirements.in         # 直接依存（手動管理）
  requirements.txt        # 全依存バージョン固定（自動生成）
  .env                    # シークレット（Git管理外）
  .env.example            # キー名テンプレート
```

---

## セットアップ

### 前提条件

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) インストール済み
- [Claude Code CLI](https://claude.ai/code) インストール・認証済み
- Discord Bot 作成済み（Send Messagesパーミッション付与）

### インストール

```bash
git clone https://github.com/KazusaNakagawa/my-world-briefing.git
cd my-world-briefing

uv venv .venv
uv pip sync requirements.txt
```

### 環境変数

```bash
cp .env.example .env
# .env を編集
```

| 変数名 | 取得先 | 用途 |
|---|---|---|
| `DISCORD_TOKEN` | Discord Developer Portal | Bot認証 |
| `CHANNEL_ID` | Discordチャンネル右クリック → IDをコピー | 送信先チャンネル |

### 実行

```bash
uv run python main.py
```

---

## 設定ファイル

### `config/briefing.json`

銘柄・テーマ・地政学リスクをすべてここで管理。コードを触らずに設定変更できる。

```json
{
  "portfolio": {
    "tickers": ["TICKER1", "TICKER2"],
    "themes": ["テーマ1", "テーマ2", "テーマ3"]
  },
  "geopolitical": {
    "conflicts": [
      {
        "name": "紛争・地政学リスク名",
        "affected_sectors": ["影響セクター1", "影響セクター2"],
        "related_tickers": ["関連銘柄1", "関連銘柄2"],
        "notes": "背景・補足メモ"
      }
    ]
  }
}
```

### `prompts/briefing.md`

プロンプトテンプレート。変数は `{tickers}` `{themes}` `{geopolitical}` `{stocks}` の4つ。
Claudeへの指示を変えたいときはこのファイルだけ編集する。

---

## 出力サンプル（Discord）

```txt
**今日のサマリー（1文）**
〜

**なぜ動いたか（ストーリー）**
〜地政学・感情・需給の観点から3〜4行で〜

**地政学と株式の因果関係**
〜地政学リスクが今日の市場に与えた影響、関連銘柄・セクターとの紐づけ〜

**自分への示唆**
〜保有者として今日意識すべきこと〜

**参考記事**
・記事タイトル — 媒体名
  https://...
```

---

## 依存パッケージ管理（uv）

```bash
# パッケージ追加時
# 1. requirements.in に追記
# 2. ロックファイル再生成
uv pip compile requirements.in -o requirements.txt
# 3. 仮想環境に反映
uv pip sync requirements.txt
```

---

## MVPロードマップ

| フェーズ | 内容 | ステータス |
|---|---|---|
| 1 | ローカルで手動実行・出力確認 | ✅ 完了 |
| 2 | Discord に飛ばして毎朝自分で受け取る | ✅ 完了 |
| 3 | AWS Lambda + EventBridge で自動化 | 🔜 次フェーズ |
| 4 | DynamoDB で銘柄・テーマを設定から切り離す | 📋 予定 |

---

## 差別化ポイント

- **既存サービスとの違い**: 情報を「出す」だけでなく、自分の銘柄・テーマ・地政学文脈で「解釈」する
- **競合空白**: 「株価変動の理由を地政学ストーリーで語る」ツールはほぼ存在しない
- **自分がユーザー零号**: 実保有株があるため、ユーザーヒアリング不要でMVPを磨ける

---

## ライセンス

MIT
