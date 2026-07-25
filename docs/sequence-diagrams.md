# Sequence Diagrams

主要フローの処理シーケンス（Mermaid）。コードを読む前の見取り図として使う。

- [1. 日次ブリーフィング（バッチ実行）](#1-日次ブリーフィングバッチ実行)
- [2. Web UI からのブリーフィング実行](#2-web-ui-からのブリーフィング実行)
- [3. ブリーフィング QA チャット（SSE）](#3-ブリーフィング-qa-チャットsse)
- [4. Journal ブレストチャット](#4-journal-ブレストチャット)
- [5. 認証とクレデンシャル解決](#5-認証とクレデンシャル解決)
- [6. チャット回答の Notion 追記](#6-チャット回答の-notion-追記)

---

## 1. 日次ブリーフィング（バッチ実行）

`bin/run.sh` → `python -m src.handler` の一本道。claude CLI 2 本を並列実行し、
メイン分析が落ちたときだけ全体を失敗させる（セクタースイープは劣化継続）。

エントリポイント: `apps/python/src/handler.py:29` (`lambda_handler`)

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Sh as bin/run.sh
    participant H as src.handler
    participant YF as fetcher.stocks
    participant G as generator.briefing
    participant CLI as claude CLI
    participant MD as notifier.local_md
    participant DC as notifier.discord
    participant NT as notifier.notion

    Op->>Sh: ./bin/run.sh
    Note over Sh: caffeinate で再 exec
    Sh->>H: python -m src.handler
    Note over H: _preflight（未設定は WARN）

    alt 当日 MD が既にある
        H-->>Sh: skipped
    else 実行する
        H->>YF: fetch_stock_moves
        YF-->>H: 前日比
        H->>G: generate_briefing

        par メイン分析
            G->>CLI: run_claude(main)
            CLI-->>G: 本文 + usage
        and セクタースイープ
            G->>CLI: run_claude(sectors)
            CLI-->>G: 本文 + usage
        end

        alt メイン失敗
            G-->>H: RuntimeError
        else セクターのみ失敗
            G-->>H: 本文 + 失敗注記
        else 両方成功
            G-->>H: 本文 + セクター動向
        end

        Note over H: looks_like_briefing で体裁検査
        H->>MD: save_briefing_md
        Note over H: index_briefings は best-effort

        opt Discord 設定済み
            H->>DC: send_to_discord
        end
        opt Notion 設定済み
            H->>NT: send_to_notion + metrics
            NT-->>H: page_url
        end
        H-->>Sh: 200 Briefing sent
    end

    opt 金曜のみ
        Sh->>H: python -m src.weekly_handler
    end
```

---

## 2. Web UI からのブリーフィング実行

POST は 202 を即返し、実処理は FastAPI の `BackgroundTasks` に載る。
フロントは `GET /api/run/{job_id}` を終端ステータスまでポーリングする。

エントリポイント: `apps/python/web/routers/run.py:55`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant W as Next.js /run
    participant PX as Next.js proxy
    participant API as FastAPI
    participant JS as src.job_store
    participant BG as BackgroundTasks
    participant H as lambda_handler

    U->>W: 実行ボタン
    W->>PX: POST /api/run
    PX->>API: 転送（Bearer 付与 / no-store）
    Note over API: require_bearer で検証
    API->>JS: create_job
    JS-->>API: status=queued
    API->>BG: add_task
    API-->>W: 202 job_id

    BG->>JS: mark_running
    BG->>H: lambda_handler（図 1）

    loop 終端まで polling
        W->>PX: GET /api/run/{job_id}
        PX->>API: 転送
        API->>JS: get_job
        JS-->>API: status
        API-->>W: queued / running / done / failed
    end

    alt 正常終了
        H-->>BG: 200
        BG->>JS: mark_done
    else 例外
        H-->>BG: Exception
        BG->>JS: mark_failed
    end
    W-->>U: 完了 / エラー表示
```

---

## 3. ブリーフィング QA チャット（SSE）

POST でジョブを作って 202 を返し、別コネクションの SSE で本文を流す 2 段構え。
SSE はバッファ全量を replay してから tail するので、途中で再アタッチしても取りこぼさない。

エントリポイント: `apps/python/web/routers/chat.py:345`（POST）/ `:485`（stream）/ `:499`（cancel）

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant W as chatStore / bridge
    participant API as FastAPI chat
    participant RAG as local_llm 検索
    participant CJS as chat_job_store
    participant BG as _run_chat_job
    participant CLI as claude CLI

    U->>W: 質問（date / search_history）
    W->>API: POST /api/chat
    Note over API: 当日 briefing MD が無ければ 404

    opt search_history=true
        API->>RAG: 過去ブリーフィング検索
        alt Ollama 未起動など
            RAG-->>API: OllamaUnavailable
            API-->>W: 503
        else 取得成功
            RAG-->>API: chunk
        end
    end
    opt Obsidian 設定済み
        API->>RAG: vault 検索
        Note over API: 失敗しても WARN のみで継続
    end

    API->>CJS: create_job
    API-->>W: 202 job_id
    W->>API: GET /api/chat/{job_id}/stream
    API-->>W: text/event-stream 開始

    BG->>CJS: mark_running
    BG->>CLI: Popen（stderr は別スレッドで drain）

    loop stdout 1 行ごと
        CLI-->>BG: stream-json
        BG->>CJS: append_event
        CJS-->>API: snapshot_events_since
        API-->>W: SSE data
        W-->>U: 逐次描画
    end

    opt 中断
        U->>W: キャンセル
        W->>API: DELETE /api/chat/{job_id}
        API->>CLI: terminate（冪等 / 常に 204）
    end

    alt returncode 0
        BG->>CJS: mark_done
    else resume 先が消えている
        Note over BG: session ファイルを削除
        BG->>CJS: stale_session → mark_done
    else その他の異常終了
        BG->>CJS: error → mark_failed
    end
    Note over BG,CJS: usage をログし猶予後に GC
```

---

## 4. Journal ブレストチャット

図 3 のジョブ / SSE 機構をそのまま再利用し、入力コンテキストの作り方だけが異なる。
直近 N 日分の journal エントリを untrusted input として system prompt に載せる。

エントリポイント: `apps/python/web/routers/chat.py:452`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant W as journalChatStore
    participant API as FastAPI chat
    participant JST as journal_store
    participant CFG as src.config
    participant CJS as chat_job_store
    participant CLI as claude CLI

    U->>W: ブレスト質問（days=7）
    W->>API: POST /api/journal/chat
    API->>JST: list_files（新しい順）

    loop 最新 days 日分
        API->>JST: read_entry
        JST-->>API: 本文
    end
    Note over API: 40k 文字で打ち切り

    alt エントリなし
        API-->>W: 404
    else あり
        API->>CFG: trusted_write_dirs
        CFG-->>API: 事前承認する書き込み先
        API->>CJS: create_job
        API-->>W: 202 job_id
        W->>API: GET /api/chat/{job_id}/stream
        API->>CLI: Popen（build_journal_cmd）
        Note over API,CLI: 以降は図 3 と同一
    end
```

---

## 5. 認証とクレデンシャル解決

API 側の Bearer と、claude サブプロセスに渡す env（`auth_mode` 依存）は別物。
`ANTHROPIC_API_KEY` を触るのは `build_env()` だけ、という不変条件を図示する。

エントリポイント: `apps/python/web/auth.py:35` / `apps/python/src/claude_runner.py:119`

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as FastAPI
    participant TK as session-token
    participant ST as src.state
    participant CR as build_env
    participant KC as credentials
    participant CLI as claude CLI

    C->>API: Bearer トークン付きリクエスト
    API->>TK: _ensure_token（無ければ生成 / 0600）
    TK-->>API: expected token

    alt ヘッダ無し
        API-->>C: 401 Missing Bearer token
    else 不一致
        API-->>C: 401 Invalid Bearer token
    else 一致
        API->>ST: read_state().auth_mode
        ST-->>API: cli または api
        API->>CR: build_env(auth_mode)
        alt cli モード（既定）
            Note over CR: ANTHROPIC_API_KEY を env から除去
        else api モード
            CR->>KC: get_credential
            KC-->>CR: Keychain → .env の順で解決
            Note over CR: env に注入
        end
        CR-->>API: env
        API->>CLI: subprocess 起動
    end
```

---

## 6. チャット回答の Notion 追記

Notion への追記ロジックは API 側ではなくローカルの `/notion-import` スキルが持つ。
エンドポイントは claude CLI サブプロセスの起動とステータス変換だけを担当する。

エントリポイント: `apps/python/web/routers/chat.py:601`

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant W as チャット画面
    participant API as FastAPI chat
    participant KC as credentials
    participant CLI as claude CLI
    participant MCP as Notion MCP
    participant N as Notion

    U->>W: Notion に保存
    W->>API: POST /api/chat/notion-import
    API->>KC: NOTION_API_KEY / DATABASE_ID
    KC-->>API: 値または未設定

    alt 未設定
        API-->>W: 400（不足キー名を明示）
    else claude CLI が無い
        API-->>W: 502 claude CLI not found
    else 実行
        API->>CLI: subprocess.run（notion-import スキル）
        CLI->>MCP: 当日ブリーフィングページを検索
        MCP->>N: query / append blocks
        N-->>MCP: page URL
        MCP-->>CLI: 結果
        alt 対象ページ無し
            CLI-->>API: 該当なし
            API-->>W: 404
        else 異常終了 / タイムアウト
            CLI-->>API: エラー
            API-->>W: 502
        else 成功
            CLI-->>API: page URL
            API-->>W: 200 url
        end
    end
    W-->>U: 保存結果を表示
```

---

## 補足

- ジョブストア（`src.job_store` / `src.chat_job_store`）はいずれもプロセス内メモリ。uvicorn を再起動すると実行中ジョブは消える。
- フロント側は画面遷移をまたいで生存させるため store + jobStore + 常駐 bridge の構成を取る（`lib/chatStore.tsx`, `lib/chatJobStore.tsx`, `lib/journalChatJobStore.tsx`）。
- claude CLI 呼び出しは必ず `src/claude_runner.py` 経由か、chat router の `build_env()` 経由。直接 `subprocess.run(["claude", ...])` を書かない（CLAUDE.md の規約）。
