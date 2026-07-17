# Web UI (Phase 1) — Setup and Operation

ローカル localhost-only な FastAPI バックエンド + Next.js フロントエンドの使い方。

## 起動

```bash
./bin/serve.sh                   # API :8000 + Web :3000 + ブラウザ自動オープン
./bin/serve.sh --no-browser      # ブラウザは開かない ($CI が立っていれば自動で skip)
API_PORT=8001 ./bin/serve.sh     # API のポートを変更
WEB_PORT=3001 ./bin/serve.sh     # Web のポートを変更

# API だけ立ち上げたい場合 (CI / Swagger 動作確認など):
./apps/python/bin/serve.sh       # FastAPI 単体
```

`bin/serve.sh` がやること:

1. **Pre-flight**: `apps/python/.venv/bin/uvicorn` と `apps/web/node_modules` の存在チェック。欠けていれば即 exit 1 + 直し方を案内
2. `.env` を `set -a; source; set +a` で読み込み
3. `~/.ai-agent/session-token` が無ければ `secrets.token_urlsafe(32)` で作成、必ず `apps/web/.token` に 0600 でミラー (両サーバが同じトークンを参照)
4. uvicorn を `--reload` 付きでバックグラウンド起動 (`apps/python/bin/serve.sh` 経由)
5. `npm run dev` をバックグラウンド起動
6. **Early-death check**: 起動直後にどちらかが死んだら（典型: ポート衝突）即 exit 1 で原因を表示
7. macOS なら `http://localhost:$WEB_PORT/` を polling し、200 が返ってから `open` (`--no-browser` または `$CI` で skip、最大 30 秒で諦め)
8. Ctrl-C で両プロセスを後始末 (`trap INT TERM EXIT` + 子孫プロセスを `pkill -P`)

未知のフラグは silent に無視せず `exit 2` で `bin/serve.sh --help` を案内する。

`--host 127.0.0.1` で localhost-only — LAN からは到達不能。

## Bearer トークン

トークンは `~/.ai-agent/session-token` に **初回認証リクエスト時に自動生成** される (`secrets.token_urlsafe(32)`、ファイルパーミッション `0600`)。手動発行は不要。

```bash
cat ~/.ai-agent/session-token    # 確認
```

### ローテート

```bash
rm ~/.ai-agent/session-token     # ファイル削除
# サーバー再起動 (Ctrl-C → ./bin/serve.sh) — 古いキャッシュを捨てる
# 次の認証付きリクエストで新しいトークンが自動生成される
```

## Swagger UI で動作確認

開発・デバッグ時の最短経路:

1. `./bin/serve.sh` をターミナル A で起動したまま
2. ブラウザで <http://127.0.0.1:8000/docs>
3. 右上の 🔒 **Authorize** をクリック → `cat ~/.ai-agent/session-token` の値を貼り付け → **Authorize**
4. これ以降、各 endpoint の **Try it out** ボタンから直接実行可能 (トークンは自動付与)

curl でやりたい場合:

```bash
TOKEN=$(cat ~/.ai-agent/session-token)
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/config
```

## エンドポイント一覧

すべて `Authorization: Bearer <token>` 必須 (`/api/health` のみ例外)。

| Method/Path | 用途 |
|---|---|
| `GET /api/health` | Bearer 不要。起動確認 |
| `GET /api/config` | `briefing.json` を返す。ファイル不在なら 404 |
| `PUT /api/config` | `briefing.json` を atomic に上書き保存 |
| `GET /api/credentials` | `{name: bool}` の set 状況。値は返さない |
| `PUT /api/credentials/{name}` | Keychain に保存 (`name` は allow-list 内のみ、ほかは 400) |
| `DELETE /api/credentials/{name}` | Keychain から削除 |
| `GET /api/auth/mode` | 現在のモード (`cli` または `api`) |
| `PUT /api/auth/mode` | モード切替。`{"auth_mode":"api"}` |
| `POST /api/run?dry_run=<bool>` | ブリーフィング非同期実行。202 + `{job_id, status}` |
| `GET /api/run/{job_id}` | ジョブ進行状況 (`pending`/`running`/`done`/`failed`) |
| `POST /api/chat` | SSE ストリーミング Q&A。`{date, question}` |

詳細スキーマは Swagger UI (`/docs`) または OpenAPI JSON (`/openapi.json`) を参照。

## 初回セットアップ手順

フレッシュチェックアウト (`apps/python/config/briefing.json` 不在) から動かすまで:

```bash
# 1. サーバー起動 — briefing.json が無くても boot は通る (lazy-load 設計、PR #60)
./bin/serve.sh

# 2. ブラウザで /docs を開き、Authorize にトークンを貼る

# 3. PUT /api/config で briefing.json を初期化
#    例 (curl):
TOKEN=$(cat ~/.ai-agent/session-token)
curl -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d @apps/python/config/briefing.json.example \
    http://127.0.0.1:8000/api/config

# 4. クレデンシャルを Keychain に保存
curl -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"value":"<your-discord-token>"}' \
    http://127.0.0.1:8000/api/credentials/DISCORD_TOKEN
#    (CHANNEL_ID / NOTION_API_KEY / NOTION_DATABASE_ID も同様)

# 5. (Optional) Claude API モードに切替
curl -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"auth_mode":"api"}' \
    http://127.0.0.1:8000/api/auth/mode
#    api モードでは ANTHROPIC_API_KEY を別途 PUT /api/credentials/ANTHROPIC_API_KEY で保存
#    cli モードのままなら Claude Code CLI の OAuth を使う (既存挙動)

# 6. 動作確認
curl -X POST -H "Authorization: Bearer $TOKEN" \
    "http://127.0.0.1:8000/api/run?dry_run=true"
#    → 202 + job_id
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/run/<job_id>
#    → "status": "done" (handler の preflight が走り credentials の有無を warn 出力)
```

## 認証モードについて (`cli` vs `api`)

- **`cli`** (デフォルト) — `claude` CLI の OAuth セッションを使う。Anthropic API キー不要、Claude Pro/Max サブスク前提。
- **`api`** — `ANTHROPIC_API_KEY` (Keychain → `.env` フォールバック) を環境変数経由で `claude` CLI に渡す。従量課金。

切替は `PUT /api/auth/mode` の 1 リクエストのみ。`~/.ai-agent/state.json` に永続化され、次のバッチ実行 (cron 経由) から即反映される (`bin/run.sh` が毎回新規 Python プロセスを起こすため、再起動不要)。

詳細は [`apps/python/src/claude_runner.py:build_env`](../../apps/python/src/claude_runner.py) を参照。

## トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| `./bin/serve.sh` で `uvicorn not found` | venv 未同期。`cd apps/python && uv pip sync requirements.txt` |
| `./bin/serve.sh` で `web dependencies missing` | Next.js 依存未インストール。`cd apps/web && npm install` |
| `GET /api/config` が 404 | `apps/python/config/briefing.json` が無い。`PUT /api/config` で作成 |
| `GET /api/config` が 500 (corrupt JSON) | `briefing.json` が壊れている。`apps/python/config/briefing.json.example` を参考に手で直すか `PUT` で再作成 |
| `POST /api/run` の job が `failed` | `GET /api/run/{job_id}` の `error` フィールドを参照。多くは `briefing.json` 不整合 or クレデンシャル不足 |
| `POST /api/chat` から `event: stale_session` が返る | 保存セッション ID が無効。同じリクエストを再送 (バックエンドが古いセッションファイルを削除済みなので新規セッションで実行される) |

## バッチ実行 (cron) との関係

このサーバーは UI/管理用のフロントエンドであり、定期実行とは独立しています。launchd でのスケジューリングは [`launchd-setup.md`](./launchd-setup.md) を参照。`PUT /api/config` で更新した内容は launchd 経由のバッチが次回起動時に自動的に反映します (毎回 `load_config()` が走るため)。
