---
name: architecting-defaults
description: Use during any technical brainstorming, design discussion, or skill like tech-architect / brainstorming when the user pushes back with "ベストプラクティスは？", "種類は？", "X を参考にしたい", multi-answer responses like "1, 3", or short-label requests. Encodes recurring decision-time behaviors so the same back-and-forth is not repeated next session.
allowed-tools: Read, Bash, AskUserQuestion, Edit, Write
---

# Architecting Defaults

技術選定インタビュー (`tech-architect`, `superpowers:brainstorming`, 設計レビュー) の中でユーザが繰り返し指摘してきた点を行動規範に変換したもの。これらは「次回も聞かれるな」というシグナル。質問する前に既にここに記述された動きをする。

## When to Apply

- 任意の質問が "ベストプラクティスは？" "推奨は？" "おすすめは？" で返答された
- 任意の選択肢提示が "種類は？" "他にある？" "全部教えて" で返答された
- ユーザが "X を参考にしたい" "Y みたいに" と参照プロジェクトを挙げた
- 質問の答えが "1, 3" のような複数選択 or "1 のうち〜の場合は 2" の条件付きで返ってきた
- UI ラベル候補を提示したら「もっと短く」「〜のみで OK」と返ってきた

## Patterns

### 1. Recommend Decisively (推奨即答)

**Trigger**: "ベストプラクティスは？" / "推奨は？" / "おすすめは？"

**動作**:
1. 質問を **再提示しない**。
2. **1 つの強い推奨** を出す。複数候補を並べて再投票させない。
3. 推奨理由を **比較表** で示す (項目数 3-5 行)。
4. 既存業界実装 (GitHub Desktop / 1Password / Vercel など) を引き合いに出す。
5. フォールバックがあれば併記 (例: 「Keychain 推奨、フォールバックで .env も読む」)。
6. 最後に「これで進めてよいですか？」で確認。

**❌ NG**: 「3 つあります、どれにしますか？」と再投票。

**✅ OK**:
> ベストプラクティスは **X** です。理由:
> | 項目 | A | B (推奨) | C |
> | ... |
> 業界では GitHub Desktop / 1Password 等が採用。これで進めてよいですか？

### 2. Compare Options First (比較表先出し)

**Trigger**: "種類は？" "全部教えて" "他にある？"
**または**: 任意のフレームワーク・ライブラリ・ツールカテゴリを提示するとき

**動作**:
1. **最初から比較表で提示する**。箇条書き羅列はしない。
2. 列: 名前 / 種類 / 特徴 / 採用例 (3-5 列)。
3. 行: 主要 5-7 選択肢に絞る (網羅すべきでない、よく使われるもの)。
4. 表の下に **推奨 1 つ + 理由 3 行**。
5. その後 `AskUserQuestion` で選択を求める。

**❌ NG**: 「Tailwind、Bootstrap、MUI、Chakra、Bulma、Foundation、Materialize、Semantic UI、Pure CSS、Tachyons、Spectre、Skeleton...」のような長いリスト。

**✅ OK**:

> | Framework | Type | 特徴 |
> |---|---|---|
> | Tailwind CSS | ユーティリティ | 自由度高い |
> | shadcn/ui | コンポーネント (Tailwind) | Vercel 推奨、ロックインなし |
> | MUI | コンポーネント | Material Design、業務系 |
>
> （主要候補を 5-7 行に絞って提示）
>
> 推奨は **shadcn/ui**。理由: Next.js との相性、ロックインなし、ダーク/ライト標準対応。

### 3. Reference Project Inspect (参照リポ先調査)

**Trigger**: ユーザが "X を参考にしたい" "Y みたいに" "Z と同じ感じで" と既存プロジェクトを挙げた

**動作**:
1. 質問を返す前に **そのリポを Read/Bash で読む** (package.json / requirements.txt / README / src/ ディレクトリ構造)。
2. スタック・採用ライブラリ・ディレクトリ構造を **表で要約**。
3. ユーザに `AskUserQuestion` で **「UX のみ参考 / スタックも揃える / 部分流用」** を聞く。
4. それから本来の質問を出す。

**❌ NG**: 「rep-xxx を参考にしたいんですね。バックエンドは何にしますか？」(リポを読まずに進む)

**✅ OK**:

> rep-xxx のスタックは下記です:
>
> | レイヤ | 技術 |
> |---|---|
> | Backend | Node.js + Express + TS |
> | Frontend | Vue 3 + Vite + Tailwind 4 |
>
> （必要に応じて他レイヤも追記）
>
> 「参考にする」範囲を確認させてください: UX のみ / スタックも揃える / どこか部分流用

### 4. Terse UI Labels (簡潔ラベル)

**Trigger**: UI のラベル・ボタン名・サイドバー項目を提案する場面、または「もっと短く」「のみで OK」と指摘された

**動作**:
1. **デフォルトは 2-4 文字の動詞**: 「実行」「保存」「削除」「設定」「履歴」など。
2. アイコン + 短い名前を組合せる: `▶️ 実行` `📊 ポートフォリオ` `🔑 認証`。
3. 「いま実行」「すぐに実行」「今すぐ始める」のような **修飾語は不要**。
4. ツールチップで補足説明 (画面上のラベルは短く、ツールチップで長く)。

**❌ NG**: 「いますぐブリーフィングを実行する」
**✅ OK**: `▶️ 実行` (tooltip: ブリーフィングを今すぐ生成)

### 5. Flexible Multi-Select (柔軟複数選択)

**Trigger**: `AskUserQuestion` の単一選択質問に対し、ユーザが "1, 3" "A と B 両方" "C を主にしつつ D も" と回答した

**動作**:
1. **再投票させない**。複数選択を **意図と解釈** する。
2. ユーザの意図を 1-2 行で **言い直し** 確認。
3. 必要なら追記の `AskUserQuestion` で **どちらが主か** を 1 問だけ確認。

**❌ NG**: 「単一選択でお願いします、もう一度どれですか？」

**✅ OK**:
> 「1 + 3」と理解しました: **デスクトップアプリ (1) を最終形にしつつ、開発期はローカル起動 + ブラウザ UI (3) で進める** という解釈で合っていますか？

### 6. Condition-Bridged Answer (条件付き回答)

**Trigger**: ユーザが "2 を目指したいが 1 のように〜の場合は 3" のような **モード切替** で回答した

**動作**:
1. **モード切替自体を 1 つの設計判断として記録**。
2. 例: 「CLI モード ⇔ API モード切替」「ローカル開発 ⇔ デスクトップ配布」。
3. 必要な実装側コストを 1 行で添える (例: 「`claude_runner` の env 制御 1 関数追加で対応可」)。

**❌ NG**: どちらか 1 つに絞らせる。

**✅ OK**:
> 「Pro サブスク (Claude Code CLI) と API キー (Anthropic) の切替可」を採用。`src/claude_runner.py` に env 制御 1 関数を追加すれば対応可。

## Quick Reference

| ユーザのシグナル | 動作 | 該当パターン |
|---|---|---|
| 「ベストプラクティスは」 | 推奨 1 つ + 比較表 | §1 |
| 「種類は」 | 比較表で先出し | §2 |
| 「X を参考に」 | リポを Read/Bash で先調査 | §3 |
| 「もっと短く」「のみで OK」 | 2-4 文字ラベル | §4 |
| 「1, 3」「両方」 | 複数選択として解釈 | §5 |
| 「2 を目指したいが〜なら 1」 | モード切替を 1 判断として記録 | §6 |

## Red Flags

これらの自分の発話は **rationalization** のサイン:

- 「3 つあります、どれにしますか？」→ §1 違反 (推奨を出していない)
- 「フレームワークの選択肢が多いので…」→ §2 違反 (絞らず羅列している)
- 「rep-xxx のスタックは何でしたっけ？」→ §3 違反 (自分で先に調べていない)
- 「いますぐ実行する (今日のブリーフィングを生成)」→ §4 違反 (修飾語過剰)
- 「単一選択でお願いします」→ §5 違反 (柔軟解釈をしていない)

## Notes

- このスキルは **行動規範**であり、出力フォーマットや具体的スタック選択は `tech-architect` / `brainstorming` 側で行う。
- ユーザが明示的に「全候補を見せて」と言った場合は §2 の 5-7 行制限を解除して構わない。
- 既存プロジェクトに **CLAUDE.md** がある場合、そこに記載のラベル・スタイルが §4 の上位ルールになる。
