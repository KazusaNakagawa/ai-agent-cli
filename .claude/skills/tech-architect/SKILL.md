---
name: tech-architect
description: Use when starting a new feature or product and needing architectural decisions on target user, distribution, stack, code layout, UI structure, credential storage, and auth. Walks the user through a fixed sequence of multiple-choice questions and produces a design doc draft with a decision matrix.
argument-hint: "<feature-brief>"
allowed-tools: AskUserQuestion, Read, Write, Edit, Bash, TaskCreate, TaskUpdate
---

# Tech Architect

新規機能・プロダクトの技術選定を、固定順の多肢選択質問でインタビューし、設計書ドラフトを生成する。`superpowers:brainstorming` の特化版で、毎回ゼロから問い直さないためのテンプレート。

## Usage

```bash
/tech-architect <feature-brief>
```

例: `/tech-architect ai-agent に非エンジニア向け Web UI を追加`

## Workflow

### 0. 前提

- `superpowers:brainstorming` の代替として動作。質問順を固定し、回答ごとに「推奨」を出して意思決定を加速する。
- 1 つの質問につき 1 メッセージ。`AskUserQuestion` ツールで多肢選択を提示し、`(Recommended)` を 1 番目に置く。
- ユーザが「ベストプラクティスは？」と返したら、即座に **推奨理由 + 表での比較** を返し、別の選択を促す（質問は再提示しない）。

### 1. ターゲットユーザー

選択肢:
- 自分・知人 (10 人前後) — `.env` 配布で十分
- 投資家・コミュニティ (数十-数百) — GitHub Release 配布
- 完全非エンジニア — ワンクリックインストール、画面で API キー取得
- 自分 1 人だが操作性向上 — UI 改善のみ

派生質問: 認証モデル
- Claude Code CLI (Pro/Max サブスク)
- Anthropic API キー
- 両モード切替 (Recommended for non-engineers)
- OAuth (Web ホスト時のみ)

### 2. 配布形態

選択肢:
- デスクトップアプリ (Tauri / Electron)
- ホスティング Web (SaaS)
- ローカル起動 + ブラウザ UI (rep-xxx 型) (Recommended)
- 既存通知先 (Notion/Discord) 上の UI のみ

複数選択可。例: 「ローカル + 将来 Tauri」。

### 3. MVP スコープ

選択肢:
- S: 設定 UI + 認証スイッチ (Recommended)
- M: S + 履歴ビューア + Q&A チャット
- L: M + 音声入力 + スケジューラ UI
- XL: L + デスクトップパッケージ

**重要**: L 以上を選んだ場合、**必ず Phase 分割を提案する**。スキル内で 1 計画 = 1 サブシステムを原則とする。Phase 分割案は表形式で。

### 4. バックエンドスタック

選択肢 (既存プロジェクトの言語を 1 番目に):
- Python + FastAPI (Recommended if existing code is Python)
- Node.js + Express/Fastify
- Rust (Tauri 一体化)
- ハイブリッド (Python バッチ + Node API)

### 5. フロントエンドスタック

選択肢:
- React + Next.js (Recommended — エコシステム最大)
- Vue + Vite (rep-xxx 同型)
- Svelte / SvelteKit
- なし (CLI のみ)

### 6. コード配置

選択肢:
- 同じリポ、`web/` 追加 (Recommended for small additions)
- 別リポ (完全分離)
- モノレポ化 `apps/python/` + `apps/web/` (Recommended for 2+ apps)

### 7. CSS フレームワーク

選択肢:
- shadcn/ui (Tailwind ベース) (Recommended for Next.js)
- Tailwind CSS のみ
- Material UI (MUI)
- Mantine

ユーザが「種類何ある？」と聞いたら、`docs/superpowers/specs/<topic>-design.md` 内に **比較表** を即座に出す:

| Framework | Type | 特徴 |
|---|---|---|
| Tailwind CSS | ユーティリティ | 自由度高、コンポーネント自作 |
| shadcn/ui | コンポーネント (Tailwind) | Vercel 推奨、ロックインなし |
| MUI | コンポーネント | Material Design、業務系 |
| Chakra UI | コンポーネント | アクセシブル |
| Mantine | コンポーネント | 最近人気 |
| Ant Design | コンポーネント | 中華圏業務標準 |
| DaisyUI | Tailwind プラグイン | クラス名で組める |

### 8. UI 構造パターン

選択肢:
- A: タブ型 (1 ページ + タブ)
- B: サイドバー型 (Recommended for 5+ pages)
- C: ウィザード型 (初回オンボーディング)
- B + C 組合せ (Recommended for non-engineer targets)

### 9. クレデンシャル保管

選択肢:
- `.env` ファイル (既存維持、開発者向け)
- **OS Keychain** (`python-keyring`) (Recommended for non-engineers)
- 暗号化 JSON
- DB (SQLite)

「ベストプラクティスは？」と聞かれたら必ず Keychain + 既存 `.env` フォールバックを推す。理由表:

| 項目 | .env | Keychain | 暗号化 JSON |
|---|---|---|---|
| 他プロセスから見える | ✅ | ❌ | ❌ |
| マスターパスワード | なし | OS 自動 | あり |
| 業界実装例 | (なし) | GitHub Desktop / 1Password / Slack | (少) |
| 実装コスト | 最小 | 小 | 中 |

### 10. Web サーバ認証

選択肢:
- 127.0.0.1 バインド・認証なし (Recommended for local-only)
- Bearer トークン (rep-xxx 同方式) (Recommended for defense-in-depth)
- ログインパスワード

### 11. スケジューラ

選択肢:
- 含めない、「実行」ボタンのみ (Recommended for Phase 1)
- cron 式 UI (サーバ内 APScheduler)
- launchd plist 生成 (OS シャットダウン中も走る)
- 外部 (GitHub Actions など)

### 12. 音声・アクセシビリティ・i18n

選択肢:
- 全部 Phase 2 以降 (Recommended)
- 音声入力のみ Phase 1 に含める (Web Speech API ならフロント完結)
- フル (音声 + i18n + a11y)

## Output

すべての回答が揃ったら、`docs/superpowers/specs/YYYY-MM-DD-<feature-slug>-design.md` を生成する。テンプレート:

```markdown
# <Feature Name> 設計書

- 作成日: YYYY-MM-DD
- 対象スコープ: Phase 1

## 1. 背景と目的
<feature-brief から展開>

## 2. ターゲットユーザー
<質問1の回答 + 認証モデル>

## 3. アーキテクチャ全体図
<ASCII 図、apps/ 構造>

## 4. UI 構造
<質問8の結果、ページ一覧>

## 5. API エンドポイント
<バックエンドスタックに応じた標準セット>

## 6. クレデンシャル管理
<質問9の結果>

## 7. エラーハンドリング
<標準項目: バリデーション、リトライ、フォールバック>

## 8. テスト方針
<標準: 既存テスト維持、API 単体、E2E 1 本>

## 9. 主要設計判断とその根拠
<決定マトリクス: すべての質問と回答>

## 10. スコープ外 (Phase 2 以降)
<MVP スコープで XL/L を選んだら Phase 分割表>

## 11. リスクと未解決事項
<最低 3 つ: 移行、ブラウザ互換、起動時間など>

## 12. 完了条件
<Done のチェックリスト>
```

その後 `superpowers:writing-plans` に引き継ぐ。

## Notes

- **質問は省略しない**: 「決めてある」と言われても明示記録するため必ず確認。
- **推奨は強く出す**: 既存コードベースや業界標準を根拠に、迷ったら 1 つを推す。
- **ユーザの自然言語回答も尊重**: 「1, 3」「ベストプラクティスは」など多肢選択を回避する答えは柔軟に扱う。
- **Phase 分割は早期に**: MVP スコープが L/XL なら設計書を書く前に分割案を提示。
- **既存スタック優先**: 「rep-xxx を参考にしたい」と言われたら **スタックを揃えるか UX だけか** を必ず確認。
- **「種類は？」への対応**: フレームワーク・選択肢の網羅性を聞かれたら **比較表** で即答。
