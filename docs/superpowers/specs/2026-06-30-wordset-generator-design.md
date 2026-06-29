# 単語セット生成エンジン統合 — Stage 1 設計書

- 日付: 2026-06-30
- 対象: `english_learn_app`（別リポジトリ）の単語セット生成機能を、本リポジトリ (`ai-agent`) の新規サービスとして統合する取り組みの **Stage 1**
- ゴール全体像（C）: Web UI 上で単語セットを生成・編集・管理し、アプリへ配信して一元管理する

## 背景・動機

`english_learn_app` は iOS(SwiftUI) + AWS CDK(VOICEVOX TTS) + 単語管理 Web(React/Vite) で構成される。
現状の単語セット生成は「別 AI ツールで JSON を生成 → 手でコピペしてインポート」という手作業で、煩わしい。

本リポジトリには `run_claude()`（claude CLI 経由・サブスク認証で API 課金なし）と `generator/` 基盤が既にあるため、
ここに生成エンジンを移植すれば、サブスク課金の範囲で単語セット JSON を生成でき、AI エージェント基盤と横断連携できる。

移管理由の詳細は judgment-loop（`~/.local/share/judgment-loop/judgments.jsonl`）に記録済み。

## 段階ロードマップ（ゴール C）

- **Stage 1（本書）**: 生成エンジンを本リポジトリへ移植。スキーマ準拠 JSON を `run_claude()` で生成。
- **Stage 2**: 生成結果をエンドポイント/共有ストレージ経由でアプリのインポートへ自動受け渡し（コピペ消滅）。
- **Stage 3**: 本リポジトリの Web に生成・編集・管理 UI を統合し C を完成。UI フレームワークは**保守品質を重視して後日選定**（理想は Swift 版の UI/UX。操作性が良かったため、それを移管先でも再現したい）。

ボイスエンジン(VOICEVOX/CDK) とクロスプラットフォーム化は別トラックとし本書の対象外。

## データスキーマ（`english_learn_app` の `word_set.json` 準拠）

```jsonc
{
  "words": [
    {
      "id": "UUID 形式",
      "word": "important",
      "meaning": "重要な",
      "phonetic": "ɪmˈpɔːr.tənt",   // 任意
      "sentences": [
        {
          "id": "UUID 形式",
          "english": "This is an important decision.",
          "japanese": "これは重要な決断だ。",
          "category": "一般的な使い方"
        }
        // 1 語あたり 5〜6 本
      ]
    }
  ]
}
```

## アーキテクチャ / モジュール構成

```
apps/python/src/generator/
  wordset_schema.py   # pydantic: WordSet / Word / Sentence
  wordset.py          # generate_wordset(): プロンプト構築 → run_claude → 検証 → 再試行 → 採番 → 書き出し
apps/python/bin/
  gen_wordset.sh      # CLI ラッパー（既存 run.sh 流儀）
apps/python/prompts/
  wordset_fewshot.json # 1 語ぶんの正解例（important）を few-shot に
apps/python/output/
  word_set_<timestamp>.json  # 既存 generate_words.py と同じ出力先慣習
```

責務分離: スキーマ定義 / 生成ロジック / CLI を分け、`wordset.py` は「入力 → 検証済み JSON」だけに集中する。

## データフロー

1. 入力: 単語リスト（`--words rarity,experience`）または テーマ（`--theme ビジネス --count 20`）
2. `wordset.py` が few-shot 付きプロンプトを組み、`run_claude()` で生成（claude CLI / サブスク認証）
3. 返却テキストから JSON を抽出 → `pydantic` でスキーマ検証
4. 検証 NG の場合、**エラー内容を添えて最大 2 回まで再生成**（壊れた JSON をコピペする事故をゼロに）
5. **id はアプリ慣習の UUID 形式で自前採番**（Claude には採番させない＝衝突回避）
6. **既存 `word_set.json` と重複語チェック**
7. OK なら `output/word_set_<ts>.json` に書き出し。既存 `word_set.json` へのマージは `--merge` フラグで任意

## 設計上の決定事項

- **id は自前採番**: Claude の出力 id は信用せず、生成側で UUID を採番。語と例文の双方に付与。
- **category は enum 制約**: 既存カテゴリ集合（一般的な使い方 / ビジネス / 日常会話 / 教育 / 家族 等）に pydantic で制約。新カテゴリは将来 enum 拡張で対応。
- **マージは任意フラグ**: 既定は新規ファイル書き出し。`--merge` 指定時のみ既存 `word_set.json` に追記し、重複語はスキップ。

## エラーハンドリング

- JSON 抽出失敗 / スキーマ検証失敗 → エラー詳細をプロンプトに添えて再生成（最大 2 回）。最終的に失敗したら非ゼロ終了し、生のレスポンスをログに残す。
- 重複語検出 → マージ時はスキップしてログ、新規時は警告のみ。
- `run_claude` 由来の例外（CLI 不在・タイムアウト等）はそのまま伝播。

## テスト

- pydantic スキーマ検証の正常系 / 異常系（pytest）。
- `run_claude` をモックし、「生成 → 検証 → 再試行」の制御フローを検証（実コールはしない）。
- id 採番・重複検出・マージのユニットテスト。
- 実コール 1 回の疎通確認は手動で別途実施（`feedback_model_selection_verification` 方針：外部 CLI 契約依存のため実装前/直後に実コールで機構を証明）。

## 非スコープ（Stage 1）

- Web UI、配信/受け渡しの自動化（Stage 2/3）。
- VOICEVOX/CDK、クロスプラットフォーム化。
- 既存 Vite 製 Web UI の取り込み判断。
