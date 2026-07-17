# システム総点検レポート: ai-agent

- **日付**: 2026-07-17
- **調査対象**: リポジトリ全体（apps/python・apps/web・bin・scripts・docs・CI）
- **前回監査との関係**: [ai-driven-dev-audit-2026-07-08.md](ai-driven-dev-audit-2026-07-08.md) は AI 駆動開発の「運用面」の監査。本レポートは「システム本体」（コード・構成・ドキュメント・依存）を対象とし、両者は補完関係。

---

## 1. 概要

| 項目 | 値 |
|------|-----|
| 言語 | Python 3.13 / TypeScript (Next.js 14 + React 18) |
| バックエンド | FastAPI + uvicorn（ローカル 127.0.0.1 限定） |
| パッケージ管理 | uv (`requirements.in` → compile) / npm |
| 規模 | ソース約 270 ファイル / 約 19 kloc |
| テスト | pytest 52 ファイル + vitest/Playwright 55 ファイル |
| CI | pytest.yml + web.yml（PR → dev） |
| 定期実行 | launchd（月次アーカイブは repo 同梱、日次ブリーフィングは手動セットアップ） |

## 2. アーキテクチャ

```bash
bin/*.sh (11本)  ── .env source + exec ──→ apps/python/bin/*.sh (11本)
                                             ├─ run.sh → python -m src.handler（日次ブリーフィング）
                                             │            └ 金曜のみ src.weekly_handler
                                             │            └ src.xss_handler は 6/18 からコメントアウト中
                                             └─ serve.sh → uvicorn web.app:app（FastAPI, Bearer 認証）

apps/web (Next.js) ── app/api/[...path]/route.ts がサーバー側で
                      Bearer トークン(.token)を付与して FastAPI へプロキシ
                      （トークンはブラウザに出ない。CORS 不要な良い設計）

src/claude_runner.run_claude() … 全 claude CLI 呼び出しの単一入口
                                 （auth_mode cli/api で env 切替、リトライ+usage 記録）
```

サブシステム: fetcher(yfinance) / generator(プロンプト構築) / notifier(Discord・Notion・local MD・journal sync) / evaluator(ブリーフィング精度評価) / metrics / charts / usage_monitor / local_llm(実験, RAG+ollama)。

## 3. 良い点（維持すべき設計）

- `run_claude()` への呼び出し集約、auth_mode による API キーの strip/inject、transient リトライ、usage 自動記録 — 設計と CLAUDE.md の記述が一致。
- Web の認証設計: トークンは `~/.ai-agent/session-token`（0600）→ Next サーバー側でのみ読取り。ブラウザ露出なし。
- `prompt_safety.py` で直接/間接プロンプトインジェクション対策（role マーカー中和 + untrusted ラップ）を明示的にモジュール化。
- 縮退運転（sector sweep 失敗でも本編配信、Discord/Notion 失敗でもローカル MD 保存を先行）。
- `state.json` のアトミック書込み、config の fixture 分離（CI が個人データに触れない）。
- テスト密度が高い（Python 52 + web 55 ファイル）。

## 4. 不備（修正推奨・優先度順）

### 4-1. ドキュメントと実体の乖離: `bin/briefing.py` はもう存在しない
6/18 の `be56f41`（bin/*.py → src/ 移動）以降、実体は `python -m src.handler --dry-run`。しかし以下が旧パスのまま:
- `README.md` の Dry-run 節: `.venv/bin/python bin/briefing.py --dry-run`
- `docs/guides/launchd-setup.md`: plist の ProgramArguments・動作確認コマンドとも `apps/python/bin/briefing.py`

**launchd を doc 通りにセットアップすると即失敗する**。最優先で更新。

### 4-2. README「run.sh は両エージェント実行」だが XSS は停止中
`apps/python/bin/run.sh` で `src.xss_handler` は 6/18 からコメントアウトされたままなのに、README のアーキテクチャ図・Batch scripts 表は「Run both agents (briefing + XSS intel)」。意図的な休止なら README に反映、そうでなければ復帰を判断する。

### 4-3. CI の穴
- `pytest.yml` に `paths:` フィルタなし → web だけの PR でも Python CI が走る（web.yml は絞れているのに非対称）。
- `pytest-cov` を依存に入れているのに CI は `pytest -v` のみでカバレッジ未計測。閾値ゲートか、少なくともレポート出力を。
- Playwright E2E（`apps/web/e2e/`）が CI 未実行。nightly か PR ラベル起動の workflow を検討。
- `web.yml` の `npm install`（`npm ci` でない）は macOS 生成 lockfile が原因とコメント済みだが、CI 上で一度 lockfile を再生成すれば `npm ci` に戻せて再現性が上がる。

### 4-4. serve.sh が常に `--reload`
開発用フラグが常時付与。launchd 等での常用を想定するなら `--reload` は `DEV=1` などでオプトインに。

### 4-5. 掃除もれ（小粒）
- リポジトリ直下の空 `node_modules/` ディレクトリ。
- `apps/python/bin/__pycache__/`（.py 撤去後の残骸）。
- `.claude/worktrees/` 空ディレクトリ（前回監査でも指摘、未対応）。
- ~~`docs/ai-driven-dev-audit-2026-07-08.md` が 9 日間 untracked のまま~~ → `docs/reports/` へコミット済み（本レポートも同ディレクトリへ移動済み）。

## 5. 無駄・重複（削減候補）

### 5-1. `anthropic` 依存はスパイクコードのみが使用
`generator/briefing_api.py`（#204 コスト検証スパイク）だけが `anthropic` と `local_llm` を参照し、production 側から wire されていない（呼び出し元は専用の `briefing_api.sh` のみ）。検証が済んでいるなら **スパイクごと削除して依存を requirements.in から外す**か、`experiments/` に隔離して主依存から切り離す。

### 5-2. local_llm サブシステム（実験）の去就
約 2,000 行 + 重い依存（chromadb / ollama / trafilatura + protobuf 互換の opentelemetry ピン留め）。6/22 以降更新なし、web からの参照なし。docs/features/local-llm.md の検証結論も出ているなら、**継続 / 凍結（依存を extras 化: `requirements-local-llm.in`）/ 削除** のいずれかを決めるとインストールと依存解決が大きく軽くなる。

### 5-3. dev 依存と runtime 依存の混在
`requirements.in` に pytest / pytest-cov が同居。`requirements-dev.in` に分離すれば launchd 実行環境の面積が減る。

### 5-4. `claude_rates.py` の二重定義
`scripts/claude_rates.py`（14 行）と `apps/python/src/claude_rates.py`（50 行）が別内容で併存。scripts 側を src 側の import に寄せて一本化。

### 5-5. journalChatJobStore が共通化に未移行
`lib/createJobStoreProvider.tsx`（250 行）への移行は chatJobStore / jobStore まで完了しているが、`journalChatJobStore.tsx`（304 行）は独自実装のまま。SSE 処理など差分はあるが、パターンは同一（#350 で確立したテンプレート）なので統合すれば `lib/` の store 8 ファイル体制がスリムになる。

### 5-6. bin ラッパー 11 本 × 2 階層
root `bin/*.sh` は全部「.env source + exec」だけの同型コード。後方互換の意図は README に明記済みなので急ぎではないが、共通ラッパー 1 本（`bin/_wrap.sh` に symlink or `exec "$(dirname $0)/../apps/python/bin/$(basename $0)"` の共通化）で 10 ファイル削れる。

### 5-7. output/ 直下の散乱
`word_set_*.json` ×3、単発調査メモ md ×3、`bk/` が `output/` 直下に混在。サブフォルダ規約（`output/wordset/`, `output/notes/`）を決めて generator 側の書き出し先も揃える。

## 6. セキュリティ所見

概ね良好（Bearer + 0600 トークン、Keychain 保管、プロンプト防御、127.0.0.1 バインド）。残る細部:

- `web/auth.py` は**既存**トークンファイルのパーミッションを検証しない（新規作成時のみ 0600）。読込み時に `st_mode` チェックを一行足すと堅い。
- `bin/serve.sh` 経由の `.token`（apps/web 用コピー）は gitignore 済みで OK。
- launchd plist に絶対パスがハードコード（コメントで明示済み・許容範囲だが、テンプレ生成スクリプト化すれば doc drift ごと解消 — §7-8 参照）。

## 7. 機能拡張アイデア

| # | アイデア | 説明 | 効果/工数 |
|---|---------|------|----------|
| 1 | 評価ループの自動化と自己参照 | `evaluate.sh extract/score/report` を launchd 週次化し、直近の的中率サマリを**翌日のブリーフィングプロンプトに注入**（「先週のマクロ観の的中率 68%、外したテーマ: …」）。エージェントが自分の予測精度を踏まえて語るようになる | 効果大 / 中 |
| 2 | 閾値アラート（日次バッチ外） | 保有銘柄が ±N% 動いたら日中でも Discord に即時 push する軽量ウォッチャー（yfinance ポーリング、claude 呼び出しなしの素通知 + 任意で1行解説） | 効果大 / 小 |
| 3 | 過去ブリーフィング横断 Q&A | chat は現状「当日 or 指定日」単位。凍結候補の chromadb 資産を転用し、全過去ブリーフィングを RAG 検索して「NVDA 関連で過去に何と言っていた?」に答える | 効果中 / 中 |
| 4 | Notion コメント → judge ループ接続 | Notion ページ上のコメント（人の感想・訂正）を吸い上げて judgment ログに変換。既存の学習ループ（judge → distill）に実データが流れ込む | 効果中 / 中 |
| 5 | 月次レビュー | weekly_handler の月次版: 月間の的中率・ポートフォリオ騰落・テーマ変遷を1ページに。月次アーカイブ launchd と同じトリガーに相乗り | 効果中 / 小 |
| 6 | 縮退運転の可視化 | sector sweep 失敗などの degraded 発生を Discord に一行警告（現状ログのみで気づけない）。usage ダッシュボードに直近の失敗率も表示 | 効果中 / 小 |
| 7 | usage ダッシュボードに月末予測 | 既存の usage_monitor 集計から当月ペースで月末コスト（API 換算）を線形予測して表示 | 効果小 / 小 |
| 8 | launchd plist ジェネレータ | `bin/install-launchd.sh` がユーザー名・repo パスを埋めて plist 生成〜load まで実行。§4-1 の doc drift の再発防止にもなる | 効果中 / 小 |
| 9 | XSS エージェントの去就決定 | 復帰させるなら run.sh 有効化 + 独立スケジュール化（週1で十分かも）。休止なら README・docs から撤去して idea doc のみ残す | 判断のみ |

## 8. 推奨アクション（優先順）

1. **doc 修正**: README / launchd-setup.md の `bin/briefing.py` 参照を `python -m src.handler` に更新、XSS 休止状態を README に反映（§4-1, 4-2）— 30 分
2. **CI**: pytest.yml に paths フィルタ + カバレッジ出力（§4-3）— 30 分
3. **依存ダイエット**: briefing_api スパイクの削除/隔離 + `anthropic` 除去、local_llm の去就決定と extras 化、dev 依存分離（§5-1〜5-3）— 半日
4. **小掃除**: 空 node_modules・__pycache__・worktrees 削除、前回監査 md のコミット、claude_rates 一本化（§4-5, 5-4)— 30 分
5. **拡張の第一手**: 効果大/工数小の「閾値アラート」(#2) か「評価ループ自己参照」(#1) を推奨

## cost

```bash
ngs  Status   Config   Usage   Stats

on

 cost:            $3.13
tal duration (API):  5m 11s
Total duration (wall): 7m 19s
Total code changes:    128 lines added, 0 lines removed
Usage by model:
    claude-haiku-4-5:  1.1k input, 44 output, 0 cache read, 0 cache write ($0.0013)
      claude-fable-5:  29 input, 16.6k output, 799.9k cache read, 74.7k cache write ($3.12)

Current session
█████████████████████████                          50% used
Resets 10:40am (Asia/Tokyo)

Current week (all models)
██▌                                                5% used
Resets Jul 17 at 7am (Asia/Tokyo)

What's contributing to your limits usage?
Approximate, based on local sessions on this machine — does not include other devices or claude.ai

Last 24h · these are independent characteristics of your usage, not a breakdown

30% of your usage came from /repo-investigate
 Heavy skills can be scoped down or run with a cheaper model via skill frontmatter.

16% of your usage came from MCP server "claude.ai Notion"
 MCP tool results stay in context for the rest of the session. /compact to flush them, or disable servers you don't need.

Skills                  % of usage
/repo-investigate              30%
/notion-import                  9%

MCP servers             % of usage
claude.ai Notion               16%

d to day · w to week

Per-model breakdown unavailable (rate limited — try again in a moment)
```
