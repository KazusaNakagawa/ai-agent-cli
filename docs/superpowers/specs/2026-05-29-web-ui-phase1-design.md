# Web UI Phase 1 設計書

- **作成日**: 2026-05-29
- **対象リポジトリ**: ai-agent
- **対象スコープ**: 非エンジニア向け Web UI の Phase 1 (設定 UI + Web サーバ基盤 + Q&A チャット + 音声入力)

---

## 1. 背景と目的

現状の ai-agent はターミナル操作可能なエンジニア向けの CLI ツールとして完成度が上がってきたが、ユーザ層を広げるには初回セットアップ (`.env` 編集、Discord/Notion トークン取得、`claude` CLI 認証など) のハードルが高い。

本仕様書は **非エンジニアでもクリック操作だけで使える Web UI** を導入するための Phase 1 設計を定義する。AI ネイティブなプロダクトである [mulmoclaude](https://github.com/receptron/mulmoclaude) の UX を参考にしつつ、既存の Python ロジック (`src/`) は変更せず再利用する方針を採る。

### Phase 分割

Phase 1 では以下を対象とする:

- Web サーバ基盤 (FastAPI) + フロントエンド (Next.js)
- 初回オンボーディングウィザード
- サイドバー型設定 UI
- 「実行」ボタン (ブリーフィングの即時起動)
- 今日のブリーフィングに対する Q&A チャット (音声入力対応)
- OS Keychain によるクレデンシャル保管

Phase 2 以降に先送りする項目は §11 を参照。

---

## 2. ターゲットユーザー

- **主**: 完全非エンジニア (PC に不慣れ、ターミナル一切触らない)
- **副**: 既存ユーザ (自分) の操作性向上

認証方式はユーザに合わせて切替できる:

- **CLI モード** (デフォルト): Claude Pro / Max サブスクの OAuth を利用 (既存仕様)
- **API モード**: Anthropic API キーを使用 (従量課金)

---

## 3. アーキテクチャ全体

```
┌──────────────────────────────────────────────────────────────┐
│                  ai-agent (monorepo)                          │
│                                                               │
│  ┌────────────────────┐         ┌──────────────────────┐     │
│  │   apps/web/        │  HTTP   │  apps/python/        │     │
│  │   (Next.js 14)     │ ──────► │  (FastAPI)           │     │
│  │   localhost:3000   │ Bearer  │  localhost:8000      │     │
│  │   shadcn/ui        │  token  │                      │     │
│  └────────────────────┘         │  既存 src/ を再利用:  │     │
│                                  │   - claude_runner    │     │
│                                  │   - handler          │     │
│                                  │   - generator/       │     │
│                                  │   - fetcher/         │     │
│                                  │   - notifier/        │     │
│                                  │   - config           │     │
│                                  └──────┬───────────────┘     │
│                                         │                     │
│                              ┌──────────┼──────────┐          │
│                              ▼          ▼          ▼          │
│                        ┌────────┐ ┌─────────┐ ┌────────┐     │
│                        │Keychain│ │ briefing│ │ claude │     │
│                        │ (OS)   │ │  .json  │ │  CLI   │     │
│                        └────────┘ └─────────┘ └────────┘     │
│                          tokens    portfolio   subprocess     │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 コード配置 (モノレポ化)

現状を以下の構造にリファクタする:

```
ai-agent/
├─ apps/
│  ├─ python/                   # 既存 src/, bin/, tests/, config/ などを丸ごと移動
│  │  ├─ src/
│  │  ├─ bin/
│  │  ├─ tests/
│  │  ├─ config/
│  │  ├─ prompts/
│  │  ├─ requirements.in
│  │  └─ requirements.txt
│  └─ web/                      # 新規 Next.js プロジェクト
│     ├─ app/                   # App Router
│     ├─ components/
│     ├─ lib/
│     ├─ public/
│     ├─ package.json
│     └─ tailwind.config.ts
├─ bin/
│  └─ serve.sh                  # 新規。両プロセス並行起動
├─ docs/
└─ skills/
```

既存の `bin/run.sh` `bin/briefing.py` 等のパスが変わるので `apps/python/bin/run.sh` 経由で呼ぶラッパを `bin/` 直下に残す (後方互換)。CI と `launchd-setup.md` のパスも更新する。

### 3.2 技術スタック

| レイヤ | 採用技術 |
|---|---|
| バックエンド | Python 3.11+ / FastAPI / Uvicorn / Pydantic v2 / python-keyring |
| フロントエンド | Next.js 14 (App Router) / React 18 / TypeScript |
| スタイリング | Tailwind CSS + shadcn/ui |
| ストリーミング | Server-Sent Events (SSE) — Q&A チャット用 |
| 起動 | `bin/serve.sh` (シェル) で `uvicorn ... &` と `next dev &` をバックグラウンド起動、両方を `wait` で待機。Ctrl-C で両方落とす `trap` を仕込む |

### 3.3 起動シーケンス

1. `bin/serve.sh` を実行
2. ランダム Bearer トークンを生成し `apps/web/.token` に書き込む (Web 側が起動時に読む)
3. Uvicorn で FastAPI を `localhost:8000` で起動
4. `next dev` で Next.js を `localhost:3000` で起動
5. ブラウザを自動オープン (`open http://localhost:3000` on macOS)
6. Next.js は `.token` を読み、すべての `/api/*` 呼出に `Authorization: Bearer <token>` を付与

---

## 4. UI 構造

### 4.1 初回オンボーディングウィザード (C パターン)

`~/.ai-agent/state.json` に `{ "onboarded": true }` が無い場合のみ表示。

| Step | 画面 | 内容 |
|---|---|---|
| 1/4 | 認証モード選択 | Claude Pro サブスク / API キー の択一。サブスク選択時は `claude login` 手順を別タブで案内 |
| 2/4 | ポートフォリオ最小入力 | tickers と themes のみ。詳細セクター・地政学は後で設定画面から追加 |
| 3/4 | 通知先 | Discord / Notion のトークン入力。空欄可 (ローカル MD のみ出力モード) |
| 4/4 | テスト実行 | `/api/run?dry_run=true` でクレデンシャル検証、成功で通常画面 (サイドバー) へ |

完了時、`~/.ai-agent/state.json` に `{ "onboarded": true, "migrated_from_env": true|false }` を記録。

### 4.2 サイドバー型設定 UI (B パターン)

通常時の画面。サイドバー項目:

| 項目 | 内容 |
|---|---|
| 📊 ポートフォリオ | `briefing.json` の `portfolio` セクション編集 (tickers / themes) |
| 🌐 監視セクター | `watch_sectors` 配列の追加/編集/削除。各セクターに tickers と notes |
| 🗺️ 地政学リスク | `geopolitical.conflicts` 配列の追加/編集/削除 |
| 📨 通知先 | Discord (Token / Channel ID) / Notion (API Key / DB ID) の管理 |
| 🔑 認証 | CLI モード ⇔ API モード切替、`ANTHROPIC_API_KEY` 入力 |
| ▶️ 実行 | ブリーフィング即時起動、ログのリアルタイム表示 |
| 💬 今日の Q&A 🎤 | 今日のブリーフィングに対するチャット、音声入力対応 |

### 4.3 Q&A チャット + 音声入力

- 画面: shadcn/ui の `Card` + `Input` + マイクボタン (`Mic` アイコン)
- 音声→テキスト: `window.SpeechRecognition` (Web Speech API、ブラウザ標準)
  - 日本語対応 (`recognition.lang = 'ja-JP'`)
  - 認識結果を `<Input>` に流し込み、ユーザが送信
- 送信: `POST /api/chat` → SSE で応答ストリーム受信 → `react-markdown` でレンダリング
- Firefox 等 Web Speech API 非対応ブラウザはマイクボタンを非表示 (`'SpeechRecognition' in window` 検出)

---

## 5. API エンドポイント

すべて `Authorization: Bearer <token>` 必須 (`/api/health` のみ例外)。

| Method/Path | 説明 | 内部呼出 |
|---|---|---|
| `GET /api/health` | 起動確認 (Bearer 不要) | - |
| `GET /api/config` | `briefing.json` 全体取得 | `src.config.load_config()` |
| `PUT /api/config` | `briefing.json` 上書き保存 (atomic write) | バリデーション後 `json.dump` |
| `GET /api/credentials` | 登録済みキー名一覧 (値はマスク) | `keyring.get_password` |
| `PUT /api/credentials/{name}` | クレデンシャル保存 | `keyring.set_password` |
| `DELETE /api/credentials/{name}` | クレデンシャル削除 | `keyring.delete_password` |
| `GET /api/auth/mode` | 現在の認証モード (`cli` / `api`) | `~/.ai-agent/state.json` |
| `PUT /api/auth/mode` | モード切替 | state.json 更新 |
| `POST /api/run` | ブリーフィング非同期実行。`?dry_run=true` で検証のみ | `src.handler.run()` を `BackgroundTasks` で |
| `GET /api/run/{job_id}` | ジョブ状況 (`pending` / `running` / `done` / `failed`) | in-memory job store |
| `POST /api/chat` | 今日の Q&A (SSE ストリーミング) | `bin/chat.py` の `build_cmd()` をライブラリ化して再利用、`claude --session-id` / `--resume` でサブプロセス起動、stdout を行単位で SSE に流す |

### 5.1 リクエスト/レスポンス例

```http
PUT /api/config
Authorization: Bearer xxx
Content-Type: application/json

{ "portfolio": { "tickers": ["PLTR", "NVDA"], "themes": [...] }, ... }
```

```http
POST /api/run
→ 202 Accepted
{ "job_id": "abc123", "status": "pending" }

GET /api/run/abc123
→ 200 OK
{ "job_id": "abc123", "status": "running", "started_at": "2026-05-29T07:00:00Z", "logs": [...] }
```

---

## 6. クレデンシャル管理

### 6.1 OS Keychain (`python-keyring`)

`service` 名は `ai-agent` 固定。エントリ:

| キー名 | 内容 |
|---|---|
| `DISCORD_TOKEN` | Discord Bot トークン |
| `CHANNEL_ID` | Discord チャンネル ID |
| `NOTION_API_KEY` | Notion Integration API キー |
| `NOTION_DATABASE_ID` | Notion DB ID |
| `ANTHROPIC_API_KEY` | API モード時のみ |

### 6.2 `.env` フォールバック

Keychain アクセス失敗時、または既存 `.env` 検知時:

1. 既存 `.env` の存在をチェック
2. 移行モーダル表示: 「.env から Keychain に移行しますか？」
3. Yes → 全エントリを Keychain に書込、`.env` は残す (戻れるように)
4. No → `.env` 読み続けるレガシーモード

### 6.3 認証モード切替の実装

`src/claude_runner.py` の `run_claude()` に env 制御を追加:

```python
def _build_env(auth_mode: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # 既存仕様 (CLI モード)
    if auth_mode == "api":
        key = keyring.get_password("ai-agent", "ANTHROPIC_API_KEY")
        if key:
            env["ANTHROPIC_API_KEY"] = key
    return env
```

`auth_mode` は `~/.ai-agent/state.json` から読む。

---

## 7. エラーハンドリング

| レイヤ | 戦略 |
|---|---|
| FastAPI ハンドラ | RFC 7807 (Problem Details) 形式の JSON でエラー返却 |
| バリデーション | API 境界に Pydantic v2 モデルを置く。既存 `src/config.py` のデータクラスは変更せず、Pydantic から `dict` 経由で読み込む。422 を返す |
| Keychain アクセス失敗 | UI に `.env` フォールバック誘導 |
| Claude CLI 5xx | 既存 `claude_runner` のリトライ機構をそのまま利用 |
| Web Speech API 非対応 | フィーチャー検出 → マイクボタン非表示 + ツールチップで案内 |
| `/api/run` ジョブ失敗 | ジョブストアに `error` 詳細保存、UI で展開可能 |
| `claude login` 未完了 | CLI モード時に検知 → UI にポップアップで案内 |

---

## 8. テスト方針

| 範囲 | ツール | ねらい |
|---|---|---|
| 既存 `src/` | pytest (現状維持) | 何も変更しない |
| FastAPI ハンドラ | pytest + `httpx.AsyncClient` | エンドポイント単体テスト (`tests/test_api_*.py`) |
| Keychain | `keyring.backend` モック | 保存/取得/削除のラウンドトリップ |
| Next.js コンポーネント | Vitest + Testing Library | ウィザード遷移、フォームバリデーション |
| E2E | Playwright (1 シナリオ) | オンボーディング → 「実行」までのハッピーパス |

E2E は最低 1 本に絞ってメンテコスト抑制。

---

## 9. 既存ユーザの移行パス

1. 初回 Web 起動時、`~/.ai-agent/state.json` 不在を検知
2. `.env` 存在チェック → あれば「Keychain に移行しますか？」モーダル
3. Yes → 全エントリを Keychain に書込、`.env` は残す
4. No → `.env` 読み続けるレガシーモード
5. ウィザード完了後 `state.json` に `{ "onboarded": true, "migrated_from_env": true|false }` 記録

既存の `bin/run.sh` `bin/briefing.py` (および launchd) はパスを `apps/python/` に更新するが、引き続き動作する。

---

## 10. 主要設計判断とその根拠

| 判断 | 採用 | 主な根拠 |
|---|---|---|
| バックエンド | Python (FastAPI) | 既存 `src/` をそのまま再利用、移植コストゼロ |
| フロント | Next.js (App Router) | エコシステム広い、Tauri との相性も良い |
| CSS フレームワーク | shadcn/ui (Tailwind) | Vercel 推奨、コードがプロジェクトに取込まれロックインなし |
| クレデンシャル | OS Keychain | GitHub Desktop / 1Password / Slack 等の業界標準、他プロセスから不可視 |
| Web サーバ認証 | Bearer トークン | mulmoclaude と同方式、ローカルでも防御層を確保 |
| 音声入力 | Web Speech API (ブラウザ標準) | サーバ実装ゼロ、Phase 1 に最適。Firefox 非対応は Phase 2 で Whisper 検討 |
| UI 構造 | 初回ウィザード (C) → サイドバー (B) | 初見ハードルを最小化しつつ通常時の拡張性を確保 |
| コード配置 | モノレポ (apps/python, apps/web) | 1 リポで管理、Phase 2 で Tauri 追加時も拡張容易 |

---

## 11. スコープ外 (Phase 2 以降)

| 項目 | 想定 Phase |
|---|---|
| Tauri デスクトップパッケージ (.dmg / .exe) | 2 |
| ブリーフィング履歴ビューア (`output/briefing/*.md`) | 2 |
| スケジューラ UI (launchd plist 生成) | 2 |
| Whisper サーバ (Firefox/Edge 対応) | 3 |
| XSS インテリエージェントの UI 統合 | 3 |
| 多言語 UI (i18n) | 3 |

---

## 12. リスクと未解決事項

| リスク | 影響 | 緩和策 |
|---|---|---|
| モノレポ移行で既存 CI/launchd パスが壊れる | 既存ユーザの自動実行停止 | パスラッパを `bin/` 直下に残す、移行 PR 内で `launchd-setup.md` 更新 |
| Web Speech API の認識精度 | Q&A 体験劣化 | Phase 1 では割り切り、Phase 2 で Whisper オプション追加 |
| Next.js の dev サーバ起動が遅い (~5-10 秒) | 初回起動体験 | `bin/serve.sh` で「起動中…」スプラッシュ表示 |
| Keychain アクセスにパスワード入力が出る環境 | 自動起動失敗 | フォールバックで `.env` 読込継続 |
| SSE が Tauri WebView で動作するか | Phase 2 統合時 | Phase 1 では通常ブラウザで動作確認、Phase 2 で別途検証 |

---

## 13. 完了条件

Phase 1 の Done 定義:

- [ ] `bin/serve.sh` で FastAPI + Next.js が起動しブラウザが自動オープン
- [ ] 初回ウィザード 4 ステップが完走し `state.json` が作成される
- [ ] サイドバー全 7 項目 (ポートフォリオ / 監視セクター / 地政学リスク / 通知先 / 認証 / 実行 / Q&A) が操作可能で、`briefing.json` への保存が反映される
- [ ] Keychain への保存/取得が動作 (`.env` フォールバック含む)
- [ ] CLI ⇔ API モード切替が反映される (`claude_runner` の env 制御確認)
- [ ] 「実行」で既存 `bin/briefing.py` 相当の処理が走り Discord/Notion/MD に出力
- [ ] Q&A チャットがマイクボタンから音声入力可、SSE でストリーミング応答
- [ ] FastAPI 単体テストと Playwright ハッピーパス E2E が緑
- [ ] 既存ユーザが `.env` のままでも壊れずに動く (後方互換)
