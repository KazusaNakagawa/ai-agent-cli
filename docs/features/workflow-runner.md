# ワークフローランナー仕様（Personal AI OS 基盤）

## 目的

使い切りの業務タスクを毎回ハンドラとして書き下ろすのではなく、**業務プロセスをワークフロー定義として宣言し、共通ランナーが実行する層**を作る。

背景は journal `2026-09-03_063252`（ChatGPT 共有会話の保存）の次の発見にある。

> 個々の作業は使い切りだけど、俯瞰すると業務フローは同じ

現状このリポジトリには「Task を受け取る → Workflow を判定する → Step を順に実行する」層が存在せず、新しい業務プロセスを1本増やすたびにハンドラをゼロから書いている。この仕様はその層を導入し、既存の briefing を最初の1本として移植する。

**ワークフローが増えても追加コストが一定に保たれること**を設計の主目標に置く（§4）。

## 現状（調査結果）

### ドメイン直書きのハンドラが5本ある

| ファイル | 役割 | 移植対象 |
|---|---|---|
| `src/handler.py` (141行) | デイリーブリーフィング（`bin/run.sh`） | ✅ パイロット |
| `src/weekly_handler.py` | 週次リキャップ + Notion コメント取り込み | 後続 |
| `src/self_agent_handler.py` | judgment ログ → ペルソナプロファイル | 後続 |
| `src/money/`, `src/portfolio_snapshot/` | 家計簿・ポートフォリオ集計 | 後続 |
| `src/xss_handler.py` | XSS インテリジェンス（現在 `run.sh` では無効） | ❌ 除外 |

`xss_handler.py` は移植対象から外す。同等の情報が bot の PR として流れてくるため代用が効いており、現に `run.sh` でも無効化されている。ワークフロー層のために動いていないコードを延命しない。

### 共通の骨格はすでに存在するが、すべて手書きで重複している

`src/handler.py` を読むと、汎用ランナーが持つべき責務がすでに個別実装として並んでいる。

- 冪等ガード — `BRIEFING_SKIP_IF_EXISTS` + `_is_degraded_md()`（L51-58）
- 「配信より前にディスクへ書く」順序保証（L84-92）
- best-effort ステップ — Chroma インデックスは失敗しても続行（L102-106）
- 部分失敗の許容（degraded mode）— `is_degraded_briefing()`
- 並列実行 — `generator/briefing.py` L208、`ThreadPoolExecutor(max_workers=2)`

さらに `src/recovery_handler.py` は `fetch_fx_context` / `fetch_stock_moves` / `generate_*` を **`handler.py` とは独立に import し直して**部分再実行を組み立てている。同じステップ列が2箇所に書かれている状態で、これはワークフロー層が無いことの直接の証拠になっている。

### 増え方の実績

`bin/` には現在14本のシェルスクリプトがある（`run.sh` `money.sh` `portfolio.sh` `self_agent.sh` …）。プロセスを1本足すたびに「ハンドラ1本 + シェル1本」が増える構造で、放置すればこのまま線形に増える。ここを止めることが §4 の目的になる。

### 使える土台

- **LLM 呼び出しは `run_claude()` に一本化済み**（`src/claude_runner.py` L272）。label / timeout / リトライ / usage ログ / 部分出力保存はすべてここにあるので、ランナー側で作り直す必要はない。
- **`src/journal_store.py`** が「`output/` 配下・1エントリ1ファイル・id にタイムスタンプ」という永続化の流儀を確立している。実行記録はこれに揃える。
- **`src/job_store.py`** は in-memory dict（単一 uvicorn プロセス前提、モジュール docstring に明記）。承認待ちでプロセスを跨いで生存する必要が出ると不足する。

### 存在しないもの

`workflow` / `incident` / 承認に相当する抽象はリポジトリ内に無い（`apps/python/src` と `docs` を grep 済み）。

## スコープ（決定事項）

| 論点 | 決定 |
|---|---|
| ワークフロー定義の記述形式 | **Python 宣言（dataclass）**。既存ステップがすべて Python 関数なのでそのまま載る。YAML + レジストリは定義と実装の二重管理になるため採らない |
| 1本目（パイロット） | **`briefing` を移植して置き換え**。並列ステップ・degraded・冪等ガードという難所を最初に通す |
| 人間の承認ゲート | **CLI 対話のみ**。Web UI / Discord 承認は後続 issue |
| レジストリ・単一 CLI 入口 | **v1 に含める**。拡張性の中核であり、後回しにすると `bin/*.sh` の線形増加が続く |

## 設計

### 1. データモデル

```python
# src/workflow/model.py
from __future__ import annotations   # Step.run が StepContext を前方参照するため必須

@dataclass(frozen=True)
class Step:
    id: str
    run: Callable[[StepContext], Any]
    best_effort: bool = False       # 失敗を warning にして続行（index_briefings 相当）
    dry_run_ok: bool = False        # dry run でも実行してよい（認証情報の preflight 等）
    skip_if: Callable[[StepContext], bool] | None = None


@dataclass(frozen=True)
class InputSpec:
    id: str
    required: bool = False
    default: Any = None
    help: str = ""


@dataclass(frozen=True)
class Workflow:
    id: str
    title: str
    steps: tuple[Step, ...]
    inputs: tuple[InputSpec, ...] = ()
    guard: Callable[[StepContext], str | None] | None = None
    # guard がスキップ理由の文字列を返したらランごとスキップする（--force で無視）
```

`inputs` はワークフロー固有のパラメータのみを宣言する。`dry_run` / `force` はランナー共通なので含めない。briefing は固有入力を持たないため `inputs=()` になる。この宣言があることで、CLI も将来の Web フォームも**ワークフローの中身を知らずに**入力を受け取れる。

**「実際には効いていないフィールド」を置かない。** 実装時（#454）に2点を確定させた。

- `Step.timeout` は**持たない**。ステップはインプロセスで同期実行されるため、壁時計での打ち切りは任意の Python を実際には中断できない。強制されているように見えて強制されないフィールドは、無いより悪い。LLM の timeout は `run_claude()` がすでに持っている
- `Step.approval` は**このモデルにまだ入れない**。承認ゲートを実装する #456 でフィールドとゲートを同時に追加する。フィールドだけ先にあると、`approval=True` と書いたステップが承認されないまま実行される状態が生まれる

代わりに `dry_run_ok` を追加した。`--dry-run` で認証情報の preflight は実行しつつ、配信を伴うステップはすべてスキップさせるために要る（§7 の briefing がまさにこの形）。

### 2. StepContext

ステップ間の受け渡しは `results[step_id]` 経由のみとし、グローバル状態を持たない。

```python
@dataclass
class StepContext:
    run_id: str
    workflow_id: str
    inputs: dict[str, Any]          # InputSpec で検証済みの固有入力
    results: dict[str, Any]         # 先行ステップの戻り値を step id で参照
    logger: Logger
```

### 3. ランナーの責務

```python
run_workflow(
    wf: Workflow,
    inputs: dict | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> RunRecord
```

1. `inputs` を `wf.inputs` に対して検証する。必須欠落**と未宣言キー**は最初のステップより前に失敗させる（未宣言キーを黙って捨てると、CLI の打ち間違いがステップ内の欠損値として遠くで表面化する）
2. `guard` を評価し、スキップ理由が返ったら `status="skipped"` で即 return（`force=True` なら評価自体しない）
3. 各 Step を宣言順に実行する
4. `dry_run` かつ `dry_run_ok=False` のステップ、および `skip_if` が真のステップはスキップする
5. `approval=True` なら実行**前**に承認を求める（§6 / #456 で追加）
6. `best_effort=True` のステップは例外を warning に落として続行、それ以外は**元の例外型のまま**伝播させてランを失敗させる（`src/handler.py` の呼び出し元が例外型とメッセージに依存しているため）
7. 各ステップの開始 / 終了 / 所要時間 / 例外 / 承認情報を `RunRecord` に記録し、永続化する（§5）

失敗して例外を投げる場合、`RunRecord` を例外の `workflow_run_record` 属性に載せる。失敗したランの唯一の痕跡が記録なので、raise で消えてはいけない。

**責務外**（明示しておく）— LLM 呼び出しとそのリトライは `run_claude()` が持つ。通知先の知識は Step の中に閉じる。ランナーはステップの順序・スキップ・承認・記録だけを見る。

### 4. ディレクトリ構成と拡張性

拡張性の判定基準を「**ワークフローを1本足すときに何ファイル触るか**」に置く。目標は**1ファイル**。

```
apps/python/src/workflow/
  model.py          # Step / Workflow / InputSpec / StepContext / RunRecord
  runner.py         # run_workflow
  record.py         # 実行記録の永続化（§5）
  approval.py       # CLI 承認（§6）
  registry.py       # 自動探索
  steps/            # 2本以上のワークフローが共有するステップアダプタ
  definitions/
    __init__.py
    briefing.py     # ← ワークフロー1本 = このディレクトリにファイル1枚
```

**自動探索でレジストリを作る。** `registry.py` は `definitions/` 配下を `pkgutil.iter_modules` で走査し、モジュール直下の `Workflow` インスタンスを集める。登録テーブルを別に持たない — 定義形式に YAML を採らなかった理由（定義と実装の二重管理）は、レジストリにもそのまま当てはまる。**編集点を2箇所に増やさない。**

**単一の CLI 入口を持つ。** ワークフローごとに `bin/*.sh` を増やさない。

```bash
bin/workflow.sh list                  # 登録済みワークフロー一覧
bin/workflow.sh run briefing [--force] [--dry-run]
bin/workflow.sh run incident --summary="Lambda でエラー"   # 固有入力は InputSpec 由来
bin/workflow.sh resume <run_id>       # 承認待ちからの再開（§6）
```

**ステップアダプタの置き場所にはルールを1本だけ置く。** `Step.run` は `StepContext` を受けるので、既存関数（`fetch_fx_context(CONFIG)` など）には薄いアダプタが要る。1本のワークフローしか使わないアダプタはその定義ファイルに置き、**2本目の利用者が現れた時点で `steps/` に引き上げる**。最初から共通ステップ置き場を設計しない — 実際の2人目を待つ。

**契約テストで規約を強制する。** 登録済みワークフロー全件に対する parametrized テストを1本置き、ワークフローが増えるほど自動で検査対象が増える形にする。

- `id` がレジストリ内で一意
- ステップ `id` がワークフロー内で一意
- `skip_if` / `guard` が `StepContext` 1引数で呼べる
- `inputs` の `required` と `default` が矛盾しない

これは「N本目を足したときに規約から外れていないか」を人間のレビューに依存させないための装置で、拡張性を主張するうえで最も実効性がある部分になる。

**一方で、機能としての拡張は先送りする。** 並列ステップ・条件分岐・ワークフロー間の呼び出しは、実際に必要とするワークフローが現れるまで作らない（§10）。ここで言う拡張性は「追加が安いこと」であって「機能が多いこと」ではない。

### 5. 実行記録の永続化

`output/workflow/runs/{workflow_id}/{run_id}.json` に1実行1ファイルで書く。`journal_store` と同じ流儀で、`output/` は gitignore 済みなので個人データが漏れない。

記録項目:

```
run_id, workflow_id, status, started_at, finished_at, inputs, skip_reason
steps[]: { id, status, duration_ms, error, skip_reason, approved_at }
```

`StepContext.results`（各ステップの戻り値）は**記録に含めない**。ブリーフィング本文まるごとが入り得るので、永続的に持ち続ける記録としては重すぎる。例外は承認ゲート付きワークフローで、その扱いは §6 に書く。

これは journal `2026-09-02_083119` で「本命」として挙げたエージェント実行のメトリクス層を、ワークフロー粒度で自動的に満たす。使えば勝手に貯まるので継続コストがかからない。

### 6. 承認ゲート（CLI）

- `approval=True` の Step に到達したら、ステップ id・入力サマリを表示して `y/n` を受ける
- **非対話環境（launchd / cron / Web の BackgroundTasks）では承認待ちに入らない。** `status="awaiting_approval"` で `RunRecord` を保存して中断し、`bin/workflow.sh resume <run_id>` で再開する
- `--approve-all` を用意する（バッチ用のエスケープハッチ、既定オフ）

**再開時に先行ステップの結果をどう復元するか。** ここが承認ゲートの実質的な難所になる。ステップ間の受け渡しは `results[step_id]` だけ（§2）なのに、中断でプロセスが落ちれば `results` はメモリごと消える。素朴に再開すると、承認されたステップが必要な値を失うか、副作用のある先行ステップを再実行するかのどちらかになる。

そこで**承認ステップを持つワークフローに限り**、中断時点までの `results` を実行記録に含めて永続化する。

- 承認ステップより前のステップの戻り値は **JSON シリアライズ可能**でなければならない。シリアライズできない値を返したステップがあった場合、中断時点で**明示的にエラーにする** — 黙って落として再開時に `KeyError` を出すより、その場で気づける方がよい
- `resume` は記録から `results` を復元して `StepContext` を組み立て、`status="done"` の記録があるステップは**再実行しない**
- 承認ステップを持たないワークフロー（briefing を含む）はこの制約を受けず、`results` は従来どおりメモリ内のみ

briefing には承認ステップが無いため、パイロットでは骨格を作って通すだけになる。実際に使われるのは後続の業務プロセスから。

### 7. briefing の移植

現 `handler.py` の各処理を Step に対応させる。

| 現 `handler.py` | Step | 属性 |
|---|---|---|
| `_preflight()` (L21) | `preflight` | `dry_run_ok=True` |
| `BRIEFING_SKIP_IF_EXISTS` + `_is_degraded_md` (L51) | `Workflow.guard` | `force` で無視 |
| `fetch_fx_context` (L63) | `fx` | — |
| `fetch_stock_moves` (L66) | `stocks` | — |
| `generate_briefing` + `looks_like_briefing` (L69-79) | `generate` | 内部の2並列は generator 側に残す |
| `save_briefing_md` (L87) | `persist` | 配信ステップより必ず前。`OSError` を自身で捕捉し `md_written` を bool で返す |
| `index_briefings` (L104) | `index` | `best_effort=True`, `skip_if=lambda ctx: not ctx.results["persist"]` |
| `send_to_discord` (L110) | `deliver_discord` | `skip_if=` 認証情報未設定 |
| `send_to_notion` (L119) | `deliver_notion` | `skip_if=` 認証情報未設定 |

**移植で挙動を変えない。** 現状 Discord / Notion 送信は best-effort ではなく例外が伝播するので、`best_effort=False` のまま移植する。ここを変えるかどうかは別 issue で判断する。

`persist` を `best_effort=True` に**しない**のも同じ理由。現状の `handler.py` (L86-95) が握り潰すのは `OSError` だけで、`best_effort=True` はあらゆる例外を握り潰してしまう。ステップ自身が `OSError` だけを捕まえて `md_written` を bool で返せば、挙動は完全に一致し、後続の `index` と戻り値の両方がその bool を参照できる。

`dry_run` はランナーが処理する。現状の `lambda_handler` は dry-run でも `_preflight()` だけは実行して認証情報の欠落を警告するので、`preflight` に `dry_run_ok=True` を付けてこの挙動を保つ。`RunRecord.status == "dry_run"` を受けて、ラッパは現在と同じ `{"statusCode": 200, "body": "dry-run"}` を返す。

### 8. 後方互換

`src/handler.py` の `lambda_handler` は**シグネチャも戻り値も変えずに残し**、中身を `run_workflow(BRIEFING, ...)` の薄いラッパにする。呼び出し元は以下の3系統。

- `apps/python/web/routers/run.py` L45-49（`BackgroundTasks` から遅延 import）
- `bin/run.sh` → `python -m src.handler`
- `apps/python/tests/test_handlers.py`, `test_api_run.py`

戻り値は `RunRecord` から組み立て直す。対応は次のとおりで、記録スキーマに専用フィールドを足す必要はない。

| 現在の戻り値 | 由来 |
|---|---|
| `md_written` | `record.results["persist"]`（`persist` ステップが返す bool） |
| `body="dry-run"` | `record.status == "dry_run"` |
| `body="skipped (already generated today)"` | `record.status == "skipped"` と `record.skip_reason` |
| `statusCode=200` | 上記いずれか。失敗時は `run_workflow` が例外を投げるのでここに来ない |

`bin/run.sh` も残す（`bin/workflow.sh run briefing` のエイリアスになる）。

### 9. テスト方針

- **ランナー単体** — 宣言順の実行、`inputs` 検証、`guard` によるスキップ、`skip_if`、`best_effort` の握り潰し、非 best-effort の例外伝播、承認待ちでの中断と `resume`、`RunRecord` の内容
- **レジストリ契約テスト** — §4 の規約を登録済み全ワークフローに対して parametrized で検査
- **briefing 移植** — `apps/python/tests/test_handlers.py` が**無改修で全部通ること**を移植成功の判定基準にする。同ファイルは `statusCode` / `md_written` / Discord・Notion の呼び出し有無 / MD の中身 / エラー時に本文が例外へ漏れないことまで検証しており、移植の回帰検知として十分な密度がある

### 10. スコープ外（後続 issue）

- Web UI での承認（`job_store` の永続化を伴う）、Discord 承認
- Skills ブリッジ — Python から `subprocess` + `claude -p` で登録済みスキルを呼ぶ
- 残りのハンドラ移植（weekly / self_agent / money / portfolio）と `recovery_handler.py` のステップ重複解消。**`xss_handler.py` は移植しない**
- 並列ステップ、条件分岐、ワークフローからワークフローの呼び出し — briefing の2並列は generator 内に閉じており、ランナー側には不要。実際に必要とするワークフローが出るまで作らない
- Web の `run.py` を汎用化して任意のワークフローを起動できるようにする（レジストリができれば実装は小さい）
