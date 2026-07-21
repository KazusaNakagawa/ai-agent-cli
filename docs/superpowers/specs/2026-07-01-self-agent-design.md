# 自分専用エージェント「self-agent」— 設計書

- 日付: 2026-07-01
- 対象: judgment-loop のログを材料に、思考パターン・根底の欲求を言語化し、Notionへ週次配信しつつ人格プロファイルを蓄積するエージェント

## 背景・動機

普段のやりとり(judgment-loopのログ: 拒否/修正/確認の記録)から、自分がどんな思考で何を作っているか、なぜそれを作っているか、市場価値を上げたい・人の役に立ちたいといった根底の欲求を言語化・整理したい。
本リポジトリには `run_claude()` とfetcher/generator/notifierの3層アーキテクチャ(`briefing`)が既にあるため、同じ型で構築する。

## アーキテクチャ

```bash
apps/python/bin/self_agent.py → apps/python/src/self_agent_handler.py
  ├── src/fetcher/judgment_log.py      # judgments.jsonl を読み込み、前回watermark以降の新規ログを抽出
  ├── src/generator/self_profile.py    # プロンプト構築 → run_claude() → 週次気づき生成 → プロファイル差分抽出
  └── src/notifier/notion.py           # 既存Notifierを流用してNotionページへ配信
apps/python/config/
  self_agent_profile.md          # 蓄積される人格プロファイル(gitignore対象)
  self_agent_profile.md.example  # スキーマ・記載例(トラッキング対象)
apps/python/output/
  self_agent_report_<ts>.md      # 週次レポートのローカル控え(既存output/慣習に合わせる)
```

責務分離: `briefing`と同型。fetcherはjudgments.jsonlの読み込みのみ、generatorはプロンプト構築とrun_claude呼び出し、notifierはNotion配信のみを担う。

## データソース

- `${JUDGMENT_LOOP_DIR:-~/.local/share/judgment-loop}/judgments.jsonl`(read-only。書き込みは行わない。dotfiles-claude側の`judgment-distill`スキルが別途rules.jsonlへ書き込むが、self-agentはそれと独立)
- 既存の`self_agent_profile.md`(前回までの蓄積プロファイル。初回はなし)
- **初回シード**: Claude Codeのプロジェクト別メモリとして既に存在する人格メモリファイル(`auto-agent-llm`リポジトリの`worldview-3d` POCが参照しているもの。会話ログ+リポジトリ観測から抽出済み)。実際のファイルパスは`.claude/projects/`配下にユーザー名・リポジトリパスを含む個人環境依存の絶対パスになるため、本書には記載しない。初回セットアップ時に手元で`self_agent_profile.md`の初期値としてコピーするのみで、以降の自動処理では再読み込みしない(手動更新分の反映が必要な場合はセットアップ時の再コピーで対応)

## データフロー

0. **(初回セットアップのみ)** 既存のClaude Codeプロジェクトメモリ人格ファイルを`apps/python/config/self_agent_profile.md`にコピーして初期値とする。以降のステップでは触れない
1. `judgments.jsonl`を読み込み、`.self-agent-watermark`ファイル(`$JUDGMENT_LOOP_DIR`配下)以降の新規ログのみ抽出
2. 新規ログ0件なら何もせず終了(ログなし週はスキップ)
3. 新規ログ + 既存`self_agent_profile.md`(あれば)をプロンプトに渡し、`run_claude()`で以下2種を生成:
   - **週次レポート**: 今週のログから読み取れる思考パターン・関心・欲求の言語化(一時的な気づき含む)
   - **プロファイル差分**: 恒常的な傾向と判断できるものだけを`self_agent_profile.md`に追記・更新する提案
4. 週次レポートは`output/self_agent_report_<ts>.md`に保存しつつ、Notionページに追記
5. プロファイル差分は`self_agent_profile.md`に反映
6. watermarkを最新処理済みログidに更新

## 設計上の決定事項

- **プロファイルファイルはgitignore**: `config/briefing.json`と同様の扱い(個人の思考・欲求という機微情報)。`.example`にはダミーのスキーマのみ残す
- **量が少ない前提の運用**: 現状`judgments.jsonl`は4件のみ。無理に一般化せず、材料が薄い週は「気づきなし」と正直に出す(過学習・こじつけの禁止)
- **judgment-distillとは独立**: dotfiles-claude側の`judgment-distill`(ログ→ルール抽出)とは目的が異なる別ツール。データソースを共有するが書き込み先・出力先は分離
- **Discordは対象外**: Notionのみに配信
- **新規ログ0件はスキップ**: 空のレポートを毎週生成しない

## エラーハンドリング

- `judgments.jsonl`が存在しない/空 → 新規ログ0件として正常終了(エラーにしない)
- `run_claude`由来の例外(CLI不在・タイムアウト等)はそのまま伝播
- Notion配信失敗 → ローカルの`output/self_agent_report_<ts>.md`は既に書き出し済みなので、レポート自体は失われない。エラーはログに残す

## テスト

- fetcherの新規ログ抽出(watermark境界)のユニットテスト
- `run_claude`をモックし、「レポート生成 → プロファイル差分反映」の制御フローを検証(実コールはしない)
- watermark更新ロジックのユニットテスト
- 実コール1回の疎通確認は手動で別途実施(`feedback_model_selection_verification`方針)

## 非スコープ

- Discord配信
- judgment-distillのルール抽出ロジックへの変更
- judgments.jsonl以外のデータソース(Claude Code会話ログ全体、手動テキスト等)の継続的な取り込み — 将来の拡張候補として保留(初回シードとなる人格メモリファイルは対象外)
- `worldview-3d`(auto-agent-llmリポジトリ)との連携・データ形式の統合 — 将来の拡張候補として保留
