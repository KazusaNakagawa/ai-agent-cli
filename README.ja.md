# My World Briefing — 個人向けマーケット・インテリジェンス・エージェント

*[English](README.md) | 日本語*

地政学イベント・株価変動・セクターテーマを毎朝収集し、特定のポートフォリオに引きつけて解釈したうえで、3分で読めるブリーフィングを Discord と Notion に配信する LLM エージェントシステム。デモではなく実運用前提で作られており、2026年4月からメンテナ本人の朝のブリーフィングとして使われている。

| | |
|---|---|
| **技術スタック** | Python 3.11–3.13 · FastAPI · Next.js 14 · TypeScript · Tailwind |
| **エージェント層** | Claude Code CLI（subprocess + WebSearch）、プロンプトの並列オーケストレーション、オプトインのローカル LLM モード（Ollama + Chroma） |
| **運用** | launchd/cron スケジューリング、デグレードモード配信、スリープ復帰後の再実行、使用量・コスト監視 |

---

## コンセプト

> 情報を*出力する*ツールではなく、自分のレンズを通して情報を*解釈する*エージェント。

Bloomberg や NewsPicks が見せるのは生のデータ。このエージェントは、すべてのイベントを自分の保有銘柄・テーマ・地政学リスクに紐づけ、「これが自分にとって何を意味するか」を毎日生成する。

ここでの本当の難所は LLM を呼ぶことではなく、**非決定的なエージェントを、毎朝無人で走らせて信頼できる水準まで持っていくこと**にある。部分障害のハンドリング、実行漏れからの復旧、昨日のモデル出力が今日のプロンプトになる構造でのインジェクション封じ込め、そしてコストの可視化。以下の設計はほぼこの制約から導かれている。

![ブリーフィングビューア](docs/screenshots/briefing-viewer.png)

<sub>Web UI のブリーフィングビューア。左が検索可能なアーカイブ、右が目次付きでレンダリングされた本文。一覧の各エントリが、無人で実行された 1 回分の朝 5 時のランに対応する。</sub>

---

## アーキテクチャ

![データフロー](docs/architecture.png)

<sub>作図元: [docs/architecture.drawio](docs/architecture.drawio) — シーケンスレベルの詳細は [docs/sequence-diagrams.md](docs/sequence-diagrams.md)</sub>

```bash
bin/*.sh → apps/python/bin/*.sh          # Python アプリへ exec する薄いラッパー

apps/python/
  src/handler.py                  # 日次マーケットブリーフィング（bin/run.sh）
  │     ├── fetcher/stocks.py     # yfinance 経由の前日比
  │     ├── generator/briefing.py # プロンプト構築、run_claude() を並列呼び出し
  │     ├── notifier/local_md.py  # 最初に output/briefing_YYYY-MM-DD.md へ書き出し
  │     ├── notifier/discord.py
  │     └── notifier/notion.py
  src/weekly_handler.py           # 週次リキャップ + Notion コメント取り込み（ワークフロー: weekly）
  src/self_agent_handler.py       # 判断ログ → ペルソナプロファイル → Notion（bin/self_agent.sh）
  src/xss_handler.py              # XSS インテリジェンスエージェント — run.sh では現在無効
  src/claude_runner.py            # claude CLI 共通ヘルパー（subprocess + WebSearch）
  web/                            # Web UI 用 FastAPI バックエンド（localhost + Bearer トークン）
  config/briefing.json            # ポートフォリオ、ウォッチセクター、地政学リスク

apps/web/                         # Next.js UI — ブリーフィング閲覧、チャット、ジャーナル、使用量モニター
```

**主要な設計判断**

- NewsAPI を使わない — リアルタイム検索は Claude Code CLI 内蔵の WebSearch が担う
- Anthropic API のトークン従量課金を使わない — Claude Code CLI の OAuth セッション上で動作するため、有効な Claude 有料プラン（Pro/Max）が必要。無料プランでは動かせない
- 地政学 → 株価の因果関係を、毎日の出力に必ず織り込む
- LLM 呼び出しの入口を 1 か所に集約 — すべての `claude` 実行は `src/claude_runner.py` を通るため、認証モード・環境変数の扱い・リトライの実装が 1 つしか存在しない

**エージェントを無人で走らせるということ**

このシステムは、LLM のステップが失敗する・ハングする・使い物にならない出力を返すことを前提にしており、かつ朝 5 時には誰も見ていないことを前提にしている。

| 懸念 | 対処箇所 |
|---|---|
| 部分障害 — セクター調査が落ちてもブリーフィング本体は届けたい | `src/handler.py` のデグレードモード。`notifier/local_md.py` がネットワーク配信より**先に**ディスクへ書き出す |
| 実行漏れ（スケジュール時刻にマシンがスリープしていた） | `bin/recover.sh` → `src/recovery_handler.py`。当日分が完成済みなら何もしない |
| プロンプトインジェクション | `src/prompt_safety.py` — `neutralize_user_text` が設定文字列中のロールマーカーを無害化し、`wrap_untrusted` が再利用される LLM 出力（昨日のブリーフィングを今日のチャットに投入するケース）を「命令ではなくデータ」として囲む |
| 一時的な API / ネットワークエラー | `src/transient_errors.py`。`claude_runner` 内でリトライ |
| コストの逸脱 | `src/usage_logger.py` / `usage_monitor.py` / `claude_rates.py`。Web UI の Monitor タブで可視化 |

<details>
<summary><b>前提条件 — スリープ中の Mac は、どんなスケジューラでも救えない。</b> 無人実行には「蓋を開けた状態 + AC 電源」が必要。満たさない場合に何が起きるかを記載。</summary>

<br>

上記はすべて、スケジュール時刻にマシンが本当に起きていることを前提としている。すなわち**蓋を開けた状態で AC アダプタに接続**していること（AC 接続時は `pmset -g custom` が `sleep 0` を返す）。蓋を閉じれば電源の種類に関係なくスリープする。

蓋を閉じたバッテリー駆動の Mac では、5 時のジョブは約 45 秒しかない DarkWake の中で起動する。claude CLI の接続が `API Error: Connection closed mid-response` で切れ、その後の一時エラーリトライが**ブリーフィングを 1 つも生成しないまま**サブスクリプションのトークンを消費する。2026-08-12 の実測で \$2 超を浪費した（[#443](https://github.com/KazusaNakagawa/ai-agent-cli/issues/443)）。`caffeinate -ims` でも防げない — `man caffeinate` にある通り `-s` は AC 電源時のみ有効で、バッテリー駆動の DarkWake を呼び出し完了まで延命できない。

このため、メンテナの環境では launchd や cron ではなく**手動実行を現行の運用としている**。詳細と実測ログは [launchd-setup.md](docs/guides/launchd-setup.md)、[cron-setup.md](docs/guides/cron-setup.md) を参照。

</details>

![使用量モニター](docs/screenshots/usage-monitor.png)

<sub>Monitor タブ。API 換算コストを日次で表示し、モデル別・プロジェクト別に内訳を出す。公表レートが存在しないモデルは、ゼロ円として黙って混ぜるのではなく合計から除外する。</sub>

---

## セットアップ

**前提:** Python 3.11〜3.13（すべて CI で実行）、[uv](https://github.com/astral-sh/uv)、認証済みの [Claude Code CLI](https://claude.ai/code)、Discord Bot、Notion インテグレーション。

```bash
git clone https://github.com/KazusaNakagawa/ai-agent-cli.git
cd ai-agent-cli
cp .env.example .env      # DISCORD_TOKEN, NOTION_API_KEY などを設定

cd apps/python
uv venv .venv
uv pip sync requirements.txt

cd ../web && npm install  # Web UI を使う場合のみ
```

環境変数と設定スキーマの全項目は [docs/guides/configuration.md](docs/guides/configuration.md) を参照。

## 実行

```bash
bin/run.sh             # 日次ブリーフィング → 週次リキャップ（金曜以外は何もしない）

# ワークフロー — 宣言済みパイプライン共通の入口
bin/workflow.sh                   # 登録済みワークフロー一覧
bin/workflow.sh run briefing      # 日次ブリーフィング
bin/workflow.sh run weekly        # 週次リキャップ。金曜以外はスキップ、--force で強制実行

# 当日のブリーフィングに対する対話 Q&A
bin/chat.sh            # 新規セッション、または再開
bin/chat.sh 2026-05-16 # 過去の特定日のブリーフィング
bin/chat.sh --list     # 保存済みセッション一覧

# ポートフォリオ・スナップショット — 構成比、為替エクスポージャー、配分ルール検査
bin/portfolio.sh            # apps/python/output/portfolio/snapshot_<date>.md へ出力
bin/portfolio.sh --stdout   # ファイル出力せず標準出力へ

# 株価比較チャート — 全保有銘柄を 100 起点に指数化、対数軸
bin/chart.sh price                                  # 保有銘柄・直近3か月
bin/chart.sh price --period 1y                      # ブリーフィングが添付する期間
bin/chart.sh price --tickers PLTR NVDA --period 5y  # 保有銘柄の代わりに任意の銘柄を指定
# apps/python/output/charts/price-comparison-<date>.png へ出力

# Web UI — FastAPI (:8000) + Next.js (:3000)、ブラウザを自動で開く
bin/serve.sh
bin/serve.sh --no-browser

# ドライラン（実行せずに認証情報だけ検証）
cd apps/python
.venv/bin/python -m src.handler --dry-run
.venv/bin/python -m src.xss_handler --dry-run
```

### バッチスクリプト（`bin/`）

`apps/python/bin/` へ `exec` する薄いラッパー。それぞれが特定のタスクに対応する。

| スクリプト | 用途 |
|---|---|
| `run.sh` | 日次ブリーフィング → 週次リキャップ（週次は金曜のみ実体が走る）。メンテナのマシンでは**手動実行が現行の運用**（[launchd-setup.md](docs/guides/launchd-setup.md#manual-execution-active) 参照）。無効化中の XSS エージェントについては[アーキテクチャ](#アーキテクチャ)を参照 |
| `workflow.sh` | 宣言済みワークフロー共通の入口。`workflow.sh` で一覧、`workflow.sh run <id>` で実行（`--force` / `--dry-run`）。個別スクリプトよりこちらを優先 — [workflow-runner.md](docs/features/workflow-runner.md) 参照 |
| `chat.sh` | ブリーフィングセッションに対する対話 Q&A |
| `serve.sh` | Web UI 一式（FastAPI + Next.js）の起動。`API_PORT` / `WEB_PORT` で上書き可 |
| `self_agent.sh` | 判断ログをペルソナプロファイル化して Notion へ投稿 |
| `briefing_api.sh` | API エントリポイント経由でブリーフィングを生成 |
| `chart.sh` | `chart.sh price` で保有銘柄の株価比較チャートを `apps/python/output/charts/` へ生成（`--tickers` で銘柄指定、`--period` の既定は `3mo`）。日次ブリーフィングは同じチャートを1年で生成し Discord メッセージに添付する |
| `portfolio.sh` | `config/holdings.json` からポートフォリオ・スナップショット（構成比、ルックスルーの為替エクスポージャー、配分ルール検査）を生成 |
| `money.sh` | 銀行明細 CSV を取り込み、月次収支をレポート — `import` / `report` / `review`。設計は [household-finance.md](docs/ideas/household-finance.md) |
| `gen_wordset.sh` | ワードセット JSON の生成（Stage 1） |
| `evaluate.sh` | ブリーフィング評価パイプラインの実行 |
| `eval_report.sh` | 抽出 → スコアリング → 評価レポート出力 |
| `local_llm.sh` | ローカル LLM モード（Ollama + Chroma） |
| `archive.sh` | 月次のブリーフィングを rclone で Google Drive へアーカイブ |
| `recover.sh` | 5 時のブリーフィングが DarkWake スリープでセクター調査を落とした場合の再実行。当日分が完成済みなら何もしない |

---

## テスト

```bash
cd apps/python && .venv/bin/pytest -v   # 1,308 ケース / 87 ファイル
cd apps/web && npm test                 # vitest（ユニット + コンポーネント）
cd apps/web && npm run test:e2e         # Playwright
```

両スイートとも push 時に GitHub Actions で実行される（[`pytest.yml`](.github/workflows/pytest.yml)、[`web.yml`](.github/workflows/web.yml)）。テストは `apps/python/tests/config/briefing.json` を読み込む。`conftest.py` が `src.config` の import より前に `BRIEFING_CONFIG_PATH` を固定するため、実行に個人設定は一切不要。

---

## ドキュメント

| トピック | リンク |
|---|---|
| 設定（環境変数、設定スキーマ、プロンプト） | [docs/guides/configuration.md](docs/guides/configuration.md) |
| 日次ブリーフィング（手動 `./bin/run.sh`、任意で launchd） | [docs/guides/launchd-setup.md](docs/guides/launchd-setup.md) |
| スケジュール実行（cron + pmset、代替手段） | [docs/guides/cron-setup.md](docs/guides/cron-setup.md) |
| ブリーフィングのアーカイブ（月次 zip → rclone で Google Drive） | [docs/guides/briefing-archive.md](docs/guides/briefing-archive.md) |
| テストと依存関係の管理 | [docs/guides/testing.md](docs/guides/testing.md) |
| Web UI のセットアップ | [docs/guides/web-ui-setup.md](docs/guides/web-ui-setup.md) |
| 使用量モニタリング（Monitor タブ、Settings > Usage、コスト試算） | [docs/guides/usage-monitoring.md](docs/guides/usage-monitoring.md) |
| ブリーフィング評価パイプライン | [docs/features/evaluation.md](docs/features/evaluation.md) |
| ジャーナル ↔ Notion 同期 | [docs/features/journal-notion-sync.md](docs/features/journal-notion-sync.md) |
| Notion コメント → 判断ログ取り込み | [docs/features/notion-comment-judgment-ingestion.md](docs/features/notion-comment-judgment-ingestion.md) |
| ローカル LLM モード（Ollama + Chroma） | [docs/features/local-llm.md](docs/features/local-llm.md) |
| シーケンス図（主要フロー） | [docs/sequence-diagrams.md](docs/sequence-diagrams.md) |
| XSS インテリジェンスエージェント（構想段階、未稼働） | [docs/ideas/xss-vulnerability-detection-agent.md](docs/ideas/xss-vulnerability-detection-agent.md) |
| レポート・監査 | [docs/reports/](docs/reports/) |

---

## ライセンス

MIT
