# Local LLM RAG Bootstrap — Design Spec

Date: 2026-06-08
Issue: [#140](https://github.com/KazusaNakagawa/ai-agent/issues/140) (Epic: [#139](https://github.com/KazusaNakagawa/ai-agent/issues/139))
Scope: Bootstrap CLI のみ。embedding 切替 (#135) / reranker (#136) / AST chunk (#138) / generation model 拡張 (#137) は後続 PR。

## Goal

`apps/python/src/local_llm/` 配下に最小の RAG サブシステムを立て、`python -m local_llm` から CLI で
リポジトリ (`~/work/ai-agent`) を index → ask できる状態を作る。後続の品質改善 4 件 (#135–#138) が乗る土台となること。

## 非ゴール

- bge-m3 / reranker / AST chunking / 大型モデル選定（#135–#138 で対応）
- Web UI / FastAPI 統合
- Claude Code / briefing / XSS エージェントへの変更

## アーキテクチャ

### パッケージ構成

```text
apps/python/src/local_llm/
  __init__.py
  __main__.py     # `python -m local_llm` のエントリ → cli.main()
  config.py       # 既定値と env override
  indexer.py      # walk → chunk → embed → upsert (content-hash で incremental)
  retriever.py    # embed query → Chroma.query → context build → ollama.generate
  cli.py          # argparse: --index / --ask / --sources / --status / --reset
apps/python/bin/local_llm.sh    # venv 検出 → `python -m local_llm "$@"` (chat.sh と同形)
bin/local_llm.sh                # ルート薄ラッパ。apps/python/bin/local_llm.sh に exec
apps/python/tests/local_llm/
  test_indexer.py
  test_retriever.py
  test_cli.py
```

### 既定設定 (`config.py`)

| キー | 既定 | env override |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | `OLLAMA_HOST` |
| `OLLAMA_MODEL` | `qwen2.5:7b` | `LOCAL_LLM_MODEL` |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | `LOCAL_LLM_EMBED_MODEL` |
| `RETRIEVAL_TOP_K` | 6 | `LOCAL_LLM_TOP_K` |
| `CHROMA_PATH` | `apps/python/.chroma_db` | `LOCAL_LLM_CHROMA_PATH` |
| `REPO_ROOT` | `~/work/ai-agent` | `--root` フラグ |
| `CHUNK_LINES` | 60 | — |
| `CHUNK_OVERLAP` | 10 | — |

### 依存追加 (`apps/python/requirements.in`)

```text
chromadb>=0.5
ollama>=0.3
```

`uv pip compile requirements.in -o requirements.txt` で `requirements.txt` を再生成する。

### .gitignore

`apps/python/.chroma_db/` を追加。

## データフロー

### Indexing (`--index`)

1. `REPO_ROOT` を `os.walk` で走査。以下を除外:
   - ディレクトリ: `.git`, `__pycache__`, `node_modules`, `.chroma_db`, `.venv`, `dist`, `build`, `.next`
   - 拡張子 allowlist: `.py .ts .tsx .js .md .json .yaml .yml .sh .toml .txt`
   - サイズ上限: 1 ファイル 500 KB 超は skip
2. 各ファイルを line-based に chunk（既定 60 行 / overlap 10 行）。#138 で AST 置換予定なので indexer 内に
   `chunk_file(path: Path) -> list[Chunk]` の単一エントリを用意し、差替え可能にする。
3. `chunk_id = sha256(source_path + ":" + start_line + "-" + end_line + ":" + content)` (hex)。
   Chroma collection に同一 `chunk_id` が既に存在すれば埋め込み・upsert を skip（内容変更時は
   id が変わるので自然に新規 upsert になる）。
4. 変更 / 新規 chunk のみ `ollama.embeddings(model=EMBED_MODEL, prompt=chunk.text)` を呼び、Chroma の
   collection `ai_agent_repo` に upsert。metadata: `{source_path, start_line, end_line}`。
5. 同一ファイル内の旧 chunk_id（今回の chunk セットに含まれないもの）は `collection.delete(where={"source_path": ...}, ids=[...])` の差分削除で消す。
6. ファイル削除検出: 今回スキャンで未出現の `source_path` を Chroma から
   `collection.delete(where={"source_path": ...})` でファイル単位削除。
7. 終了時に集計を stdout:
   ```
   indexed N files, M chunks (added X, updated Y, deleted Z) in T.Ts
   ```

### Asking (`--ask "質問"`)

1. 質問を embed → `collection.query(query_embeddings=[v], n_results=top_k)`。
2. `build_context_text(results)` で次の形式に整形:
   ```
   [apps/python/src/foo.py:120-180]
   <chunk text>
   ---
   ```
3. プロンプト雛形（日本語固定）:
   ```
   以下のコード断片だけを根拠に、日本語で質問に答えてください。
   断片に書かれていないことは推測せず「分からない」と答えてください。
   回答の末尾に Sources: として参照ファイル名を列挙してください。

   ## Context
   {context}

   ## Question
   {question}
   ```
4. `ollama.generate(model=OLLAMA_MODEL, prompt=..., stream=True)` で stdout にトークンストリーム。
5. 末尾に `Sources:` として top-k のユニーク `source_path:start-end` を表示。

### `--sources "質問"`

generate を呼ばず retrieval だけ実行し top-k の `source_path:start-end` と距離スコアを表形式で出す。
retrieval デバッグ用。

## CLI

```text
python -m local_llm --index [--root PATH] [--reset]
python -m local_llm --ask "質問" [--top-k 6] [--model qwen2.5:7b]
python -m local_llm --sources "質問" [--top-k 6]
python -m local_llm --status
```

- `--reset` は `.chroma_db/` を消して全件再構築。実行前に y/N 確認プロンプトを出す。
- `--status` は index 件数 / 使用 model / chroma path を表示。
- `bin/local_llm.sh` は `bin/chat.sh` と同じ pattern: venv 検出後 `python -m local_llm "$@"` を exec。

## エラーハンドリング (システム境界のみ)

- **Ollama 未起動**: 起動時に `ollama.list()` を呼び、接続失敗なら
  `Error: Ollama に接続できません。'ollama serve' を起動してください` を stderr に出して `exit 1`。
- **モデル未 pull**: `ollama.list()` 結果と照合し、必要モデルが無ければ
  `Error: model 'qwen2.5:7b' not found. Run: ollama pull qwen2.5:7b` で `exit 1`。embed model も同様。
- **Chroma 書き込み失敗** (disk full 等): 例外を raise してそのまま traceback を出す。CLI なので可視性で十分。
- **top-k が空**: `--ask` 時に retrieval 結果が 0 件なら「該当する文脈が見つかりませんでした」を出して generate せず `exit 0`。

内部関数間のバリデーション・防御的チェックは入れない。

## テスト

`apps/python/tests/local_llm/` 配下。

| ファイル | テスト内容 |
|---|---|
| `test_indexer.py` | tmp_path に 3 ファイル作成 → chunk 件数 / content-hash skip / 削除検出を検証。`ollama.embeddings` は `monkeypatch` で固定ベクトル返すスタブに差替え。 |
| `test_retriever.py` | スタブ Chroma collection を inject、`build_context_text()` の整形・top-k 制御を検証。 |
| `test_cli.py` | `--status` / `--sources` を `capsys` で出力検証。Ollama 呼び出しは monkeypatch で潰す。 |

実 Ollama 必須のテストは `@pytest.mark.integration` を付けて pytest 既定では除外。CI に影響しないこと。

## ドキュメント

ルート `README.md` に「Local LLM (experimental)」セクションを追加:

- prerequisites: `ollama pull qwen2.5:7b` / `ollama pull nomic-embed-text`
- CLI 使用例 (`--index`, `--ask`, `--sources`, `--status`)
- Chroma data は `apps/python/.chroma_db/` に保存・gitignore 済み

## 受け入れ条件 (Issue #140)

- [ ] `python -m local_llm --index` がローカル Ollama 起動下で `~/work/ai-agent` を index できる
- [ ] `python -m local_llm --ask "認証はどう動く？"` が回答 + Sources を返す
- [ ] 2 回目の `--index` が unchanged ファイルを skip する (content-hash 確認)
- [ ] PR 本文に #135–#138 で再利用する 3 ベースラインクエリの before/after 結果を貼る
  - クエリ候補:
    1. ブリーフィングは何のスケジュールでどう動く？
    2. Web UI のチャットはどこからジョブを起こす？
    3. `run_claude()` の auth_mode 切替の流れは？

## 後続 Issue との接続点

- `indexer.chunk_file()` を 1 関数にまとめ、#138 (tree-sitter) で差替え可能にしておく
- `config.OLLAMA_EMBED_MODEL` を env で差替え可能にしておき、#135 (bge-m3) で切り替えるだけにする
- `retriever.retrieve()` の戻り値型を `list[RetrievedChunk]` で固定し、#136 (reranker) で間に reranker 層を挿入できる構造にする
- `config.OLLAMA_MODEL` の env override で #137 (qwen2.5:32b 等) の差替えを賄う
