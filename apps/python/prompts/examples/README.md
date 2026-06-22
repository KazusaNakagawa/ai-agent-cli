# Prompt Assets (few-shot examples)

高性能モデル（サブスク期に利用可能な上位モデル）の出力を固定アセットとして捕捉し、
将来より安価なモデル（`DEFAULT_MODEL` の Haiku やローカル Ollama）へ差し替えても
品質劣化を最小化するための few-shot 例を置く（Issue #192 / Epic #194）。

## アセット一覧

| ファイル | 対象タスク | 消費する generator |
|---|---|---|
| `briefing_few_shot.md` | メインブリーフィング本文の構成・深さ・引用スタイルの参照例 | `src/generator/briefing.py` の `generate_briefing()`（`prompts/briefing.md` の `$few_shot` に注入） |

## 各アセットの方針

- **内容ではなく「型」を示す**: 例の事実内容は古くなる前提。モデルには「最新情報で書き直すこと」を
  `prompts/briefing.md` 側で明示しており、ここでは出力フォーマット・因果の説明粒度・銘柄別示唆の
  書き方・参考記事の付け方だけを学習させる。
- **プレースホルダを含めない**: few-shot は `render()` の **値** として渡るため `$` を含んでも
  再解釈されない（単一パス置換）。ただし可読性のため `$` を含む生データ（価格表記など）は避け、
  「3% 高」のような相対表現で書く。

## 再生成・更新手順

出力フォーマットや生成ロジック（`prompts/briefing.md`、`generate_briefing()`）を変えたら、
この例も追従させる:

1. 最新の `prompts/briefing.md` で高性能モデルに 1 回ブリーフィングを生成させる
   （例: `CLAUDE_MODEL=<上位モデル> bin/run.sh`、または手動で `claude -p`）。
2. 得られた出力から固有名詞・日付・具体数値を一般化し、構成だけ残す形に整える
   （特定日の相場観をそのまま残さない）。
3. `briefing_few_shot.md` を置き換え、`prompts/briefing.md` の出力フォーマットと
   見出し階層が一致しているか確認する。
4. `pytest tests/test_generator_briefing.py tests/test_prompt.py` が通ることを確認する。
