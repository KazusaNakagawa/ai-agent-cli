# AI 駆動開発 運用精査レポート（2026-07-08）

対象: 本リポジトリ（ai-agent）+ Global Claude Code（`~/.claude/` / `dotfiles-claude`）

## 総評

**AI 駆動開発は「できている」— 平均を大きく上回る運用。** 設定のコード化（dotfiles 同期）、スキルの二層管理（global / project）、判断学習ループ（judge）、メモリ運用、spec→plan→issue→PR の開発フローまで一貫している。一方で **未使用スキルの常駐・二重管理の drift・学習ループの後段停止** という「作ったが回っていない」箇所が無駄として残っている。

## できている点

| 領域 | 評価 | 根拠 |
|---|---|---|
| 設定のコード化 | ◎ | `~/.claude/settings.json` と `dotfiles-claude/settings.json` が完全一致（diff なし）。hooks・deny リスト・plugins まで版管理 |
| 開発フロー | ◎ | git 履歴が spec → implementation plan → feature 単位コミットの順（#350 系）。issue-create / start / review-fix スキルでフロー全体をスキル化 |
| 学習ループ (layer 1) | ○ | `judge` CLI + SessionStart hook（judge-recall）が稼働。8 件記録済み |
| メモリ運用 | ◎ | 17 件、feedback/project/reference が適切に分類。索引 1 行 + 本文分離の設計通り |
| プロジェクトスキル | ◎ | `.claude/skills/` に 5 スキルを repo 同梱、README に install / drift 注意まで文書化 |
| 安全設定 | ○ | deny リスト（sudo / rm -rf / force push / reset --hard 等）が global で強制 |
| CI | ○ | pytest.yml + web.yml。テスト設定ルール（fixture config）も CLAUDE.md で明文化 |

## 無駄・改善ポイント（優先度順）

### 1. Cloudflare 系スキル 9 個が全セッションに常駐（最大の無駄）

`~/.claude/skills/` の agents-sdk / cloudflare / cloudflare-email-service / durable-objects / sandbox-sdk / turnstile-spin / web-perf / workers-best-practices / wrangler（合計 約2,300 行、wrangler だけで 922 行）。**このリポには Cloudflare 利用ゼロ**（Python + Next.js）。全プロジェクトのスキル一覧・コンテキストを毎回汚染している。

→ **対処**: Cloudflare を使うプロジェクトの `.claude/skills/` へ移すか、使う時だけ有効化するプラグイン化。

### 2. notion-import の二重管理 drift（README の警告どおり発生）

project 版（`.claude/skills/notion-import`）と global 版が**既に diff あり**。global 版だけに「確認なし・自動追記ポリシー」（memory の feedback とも一致する正）が入っており、project 版は古い。README 自身が「copy は drift する、symlink 推奨」と書いているのに copy 運用になっている。

→ **対処**: global 版の内容を project 版に反映してコミット → global を symlink に置換。

### 3. 学習ループの layer 2（judgment-distill）— ~~未稼働~~ → **稼働確認済み（当初指摘は誤り）**

初回調査で dotfiles 内に `rules.jsonl` が見つからず未稼働と判断したが、実体は `~/.local/share/judgment-loop/` にあり 7/6 に初回 distill 済みだった。7/8 に追加 distill を実行し、ルール 7 件（active 1 / tentative 6）・watermark 最新化済み。

→ **残タスク**: tentative 6 件のエビデンスが溜まったら activate 判断。週次 distill の習慣化。

### 4. 同一知識の三重定義

「architecting 中の応答ルール」が (a) memory `feedback_architecting_interview` (b) project skill `architecting-defaults` (c) `tech-architect` 内、の 3 箇所に分散。notion-import の no-confirm も memory と skill の両方にある。修正時に不整合リスク。

→ **対処**: スキルを正とし、memory はスキルへのポインタ 1 行に縮約。

### 5. ブランチ規約の自己違反

CLAUDE.md は `feat/` `fix/` … を規定しているが、現在のブランチは `feature/issue-350-...`。また memory では「feature の分岐元・PR base は dev」だが CLAUDE.md には未記載（main が示唆される）。**規約が 2 箇所で食い違い、実運用が両方からズレている。**

→ **対処**: CLAUDE.md にブランチフロー（dev 基点）を明記し、prefix を実態に合わせて統一。

### 6. 細かい掃除

- `.claude/settings.local.json.bk`（4 月の古いバックアップ）— 削除。git 管理があるので .bk 不要。
- `.claude/worktrees/` 空ディレクトリ — 削除可。
- global permissions の `Bash(*)` allow は deny リストで実害は抑えているが、`acceptEdits` + `Bash(*)` の組合せは事実上フル自動。意図的なら OK（意図の明文化を dotfiles README に一行）。
- コマンド（req-full 系 13 個）は設計提案業務用としてまとまっているが、`repo-investigate` 系 3 つは full が他 2 つを包含。単体を使っていなければ full だけ残す選択肢あり。

## 推奨アクション（要約）

1. ~~Cloudflare 系スキルを global から退避~~ → **対応済み（7/8: 8 スキル退避、web-perf は汎用のため残置）**
2. ~~notion-import drift 解消 + symlink 化~~ → **対応済み（7/8: project 版同期コミット + global を dotfiles への symlink 化）**
3. ~~judgment-distill 初回実行~~ → **稼働確認済み・7/8 追加 distill 実行**。残: 週次習慣化
4. memory ↔ skill の重複を「スキル正・memory ポインタ」に整理
5. ~~CLAUDE.md にブランチ prefix 統一~~ → **対応済み（`feature/` に修正）**。残: dev 基点フローの明記
6. `.bk` ファイル等の掃除
