# ブリーフィング評価基盤 設計（A起点 / マクロ・テーマ単位）

## 背景・目的

日次ブリーフィング（`apps/python/src/generator/briefing.py` が出力する `output/briefing/*.md`）は、
地政学・マクロの因果説明と前向きな投資示唆を自由文で提示している。しかし「その見立ては当たったか」を
後追いで測る仕組みが無く、ブリーフィングの質を定量的に改善できない。

本基盤は、過去のブリーフィングからテーマ（予測・因果主張）を構造化抽出し、後日のブリーフィングを真値
（ground truth）として LLM-as-judge で採点する。これにより的中率を時系列で観測できるようにする。

将来的にはマルチエージェント・ディベート（強気/弱気/中立）の判断生成を本基盤で定量比較する土台にする
（本 spec のスコープ外）。

## スコープ

### In scope
- ブリーフィング `.md` からのテーマ構造化抽出
- 後日ブリーフィングを真値とした LLM-as-judge 採点
- 的中率の集計レポート（type別 / セクター別 / 時系列）
- CLI エントリポイント

### Out of scope（YAGNI）
- 市場データ API による客観採点（将来の拡張: ground truth source B）
- matplotlib 等による PNG グラフ出力（視覚化は Mermaid 埋め込みで足りる）
- DB / Web UI / 通知連携
- ディベートエージェントなどの判断生成側

## 設計方針

- 新パッケージ `apps/python/src/evaluator/` を `generator` と分離して作る。
- LLM 呼び出しは全て既存の `src.claude_runner.run_claude` を経由する（CLI=サブスク経路で課金ゼロ、
  `subprocess.run(["claude", ...])` を直接呼ばない）。
- マクロ・テーマ単位で採点する。個別銘柄の正確な価格変動は当てに行かず、セクター/テーマの方向性で
  ○×を付ける。これにより真値が「後日ブリーフィングの記述」で足りる。
- 永続化は JSON ファイルのみ（DB なし）。既存 `output/briefing/*.md` をそのまま教師データとして使う。

## アーキテクチャ

3ステップのパイプライン。各ステップは独立に実行・テスト可能。

```
output/briefing/*.md
        │
   (1) extract.py        LLM抽出
        ▼
output/eval/claims/<date>.json     ← テーマ構造化レコード
        │
   (2) score.py          LLM-as-judge（後日ブリーフィングを真値）
        ▼
output/eval/scores/<date>.json     ← 判定レコード
        │
   (3) report.py         集計
        ▼
output/eval/report.md              ← 的中率スコアカード
```

### 1. 抽出 `extract.py`

入力: ブリーフィング `.md` 1本（日付 D）。
処理: `run_claude` にプロンプト（`prompts/eval_extract.md`）+ 本文を渡し、テーマの JSON 配列を得る。
出力: `output/eval/claims/<D>.json`。

テーマレコード:
```json
{
  "id": "2026-06-17-01",
  "theme": "高PER成長株に割引率上昇の重し",
  "direction": "弱気",
  "targets": ["PLTR", "MSFT", "成長株全般"],
  "horizon_days": 5,
  "type": "prediction"
}
```
- `direction`: `強気` | `弱気` | `中立`
- `type`: `prediction`（前向きの示唆）| `causal`（因果主張）。器は共通、区別はこのフィールドのみ。
- `horizon_days`: 検証ホライズン。抽出時に LLM が見立てる（既定レンジ 1〜10、無ければ 5）。

### 2. 採点 `score.py`

入力: claims ファイル（日付 D）。
処理: 各テーマについて検証窓 `(D, D + horizon_days]` に入る後日ブリーフィングを収集。窓を満たす後日
データが揃っていれば、`run_claude` に「元テーマ + 窓内の後日ブリーフィング本文」を渡して判定させる
（プロンプト `prompts/eval_judge.md`）。
出力: `output/eval/scores/<D>.json`。

判定レコード:
```json
{
  "id": "2026-06-17-01",
  "verdict": "hit",
  "confidence": 0.7,
  "rationale": "6/20・6/22 のブリーフィングで PLTR/MSFT の調整と利上げ観測継続を確認"
}
```
- `verdict`: `hit` | `miss` | `partial` | `unresolved`
- 窓内に後日ブリーフィングが1本も無い場合は `unresolved` で保留（採点せず、後で再実行時に再評価）。

### 3. レポート `report.py`

入力: `output/eval/scores/*.json` 全件。
処理: `unresolved` を除いた確定スコアを集計。
出力: `output/eval/report.md`（Mermaid 図を埋め込んだマークダウン）。

集計軸:
- type別（prediction / causal）の的中率
- セクター/銘柄群別の的中率（`targets` を正規化して集計）
- 時系列（日付ごとの hit率の推移）

partial は 0.5 hit として加重。

### 視覚化（Mermaid・依存ライブラリ追加なし）

グラフは Mermaid をマークダウンに直接埋め込む。GitHub・Notion ともにレンダリングするため、
既存の notion-import 連携ともそのまま噛み合う。新規 Python ライブラリは不要（集計は既存の
pandas/numpy で足りる）。

- type別・セクター別の的中率内訳: `pie` チャート
- 時系列の hit率推移: `xychart-beta`（折れ線）
- 数値の裏付けとして、各図に対応する集計テーブル（マークダウン）も併記する

Mermaid 文字列は `report.py` 内のヘルパで集計値から組み立てる（テンプレートに数値を流し込む
だけで、外部描画プロセスは走らせない）。

将来、より自由度の高い折れ線・棒グラフが必要になれば `matplotlib`（PNG出力）を後付けする
（本 spec ではスコープ外）。

## エントリポイント

- `apps/python/bin/evaluate.sh` → `python -m src.evaluator <subcommand>`
- サブコマンド: `extract [date|all]` / `score [date|all]` / `report`
- 既存 `briefing_api.sh` と同じ venv activate + PYTHONPATH パターンに揃える。

## エラーハンドリング・冪等性

- 抽出が空配列を返したら、その日はテーマ無しとして空 claims を保存しスキップ可能にする。
- `extract` / `score` は既に確定済み（scores が `unresolved` 以外）のレコードを再生成しない。
  `unresolved` のテーマだけ再実行時に再採点する。
- LLM 応答が不正 JSON の場合はそのファイルをスキップしログに残す（パイプライン全体は止めない）。
- 真値となる後日ブリーフィングが未生成のうちは `unresolved` のまま蓄積し、日が経って窓が満たされた
  時点で確定する。

## データ配置

| パス | 内容 | Git |
|---|---|---|
| `output/eval/claims/<date>.json` | 抽出テーマ | Ignored |
| `output/eval/scores/<date>.json` | 採点結果 | Ignored |
| `output/eval/report.md` | スコアカード | Ignored |
| `apps/python/prompts/eval_extract.md` | 抽出プロンプト | Tracked |
| `apps/python/prompts/eval_judge.md` | 採点プロンプト | Tracked |

`output/` は既存方針に従い ignore（教師データ・成果物はコミットしない）。

## テスト戦略（TDD）

`run_claude` をモックして決定的にテストする。

- 抽出: モック LLM 応答（JSON配列）→ claims レコードに正しくパースされる／不正JSONはスキップ。
- 採点: 検証窓のブリーフィング収集ロジック（窓内/窓外の判定）／窓を満たさないと `unresolved`／
  モック判定応答が verdict レコードに反映される。
- レポート: 既知の scores 群 → type別・セクター別・時系列の集計値が正しい／partial=0.5加重／
  `unresolved` 除外。
- 冪等性: 確定済みレコードは再生成されず、`unresolved` のみ再採点対象になる。

## 未確定事項

なし（市場データ採点・ディベート連携は意図的に後続スコープ）。
