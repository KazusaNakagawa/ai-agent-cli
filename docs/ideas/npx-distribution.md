# npx distribution (`npx brief-lens`)

> **Status: implemented** (#485–#488). User-facing docs: [docs/guides/npx-quickstart.md](../guides/npx-quickstart.md).
> This note keeps the original design rationale; the guide is the source of truth for current behavior.

Goal: let a new user start the Web UI with a single command, without cloning the repo,
in the same spirit as `npx mulmoterminal`.

```bash
npx brief-lens            # bootstrap on first run, then start API + Web UI and open the browser
npx brief-lens --help
```

## Constraints found in the current code

| Area | Today | Problem for npx |
|---|---|---|
| Data paths | `Path(__file__).parents[...]` → `apps/python/{config,output,log,input}` (~20 call sites) | The npm package lives in the npx cache — read-only in spirit and wiped on upgrade |
| Session token | `~/.ai-agent/session-token`, mirrored to `apps/web/.token` by `bin/serve.sh` | Launcher must own this instead of a shell script |
| Web UI | `next dev` only | Needs a production build shipped inside the package |
| Python deps | `uv venv` + `uv pip sync` by hand | Must be automatic on first run |
| Name | `ai-agent-cli` is taken on npm | Package name is `brief-lens` |

## Design

### 1. Data home

- New module `apps/python/src/paths.py` is the single source for writable locations.
- `BRIEF_LENS_HOME` env var selects the root. Unset → current in-repo layout
  (`apps/python/`), so clone users and CI see no change.
- The npx launcher sets `BRIEF_LENS_HOME=~/.brief-lens`. Layout under it:
  `config/`, `output/`, `log/`, `input/`, `runtime/venv/`, `session-token`.
- Read-only assets (`prompts/`, `*.example`) stay resolved relative to the package.

### 2. Web UI build

- `next.config.mjs` → `output: "standalone"`; the package ships `.next/standalone` + static assets.
- Launcher runs `node server.js` from the standalone dir with `PORT`, `AI_AGENT_TOKEN_PATH`
  and the API base URL in env.

### 3. Launcher (`packages/brief-lens/bin/brief-lens.mjs`)

1. Pre-flight: Node >= 18, `uv` on PATH, `claude` on PATH — each missing item prints
   the install command and exits non-zero.
2. First run: create `~/.brief-lens/`, copy `*.example` configs, generate the session token (0600).
3. Python: `uv venv` + `uv pip sync requirements.txt` into `runtime/venv`, skipped when the
   lock hash is unchanged.
4. Start uvicorn (no `--reload`) and the Next standalone server; open the browser; Ctrl-C stops both.
5. Flags: `--port`, `--api-port`, `--no-browser`, `--home <dir>`, `--version`, `--help`.

### 4. Packaging and release

- Package root assembled by a build script (`scripts/build-npm.mjs`): launcher + standalone web
  build + `apps/python/{src,web,prompts,config/*.example,requirements.txt}`.
- CI: `npm pack` smoke test — install the tarball in a temp dir and run `brief-lens --version`
  and a `--no-browser` boot until `/api/health` answers.
- Publish from a `v*` tag via GitHub Actions (manual approval; not automated from `dev`).

### 5. Docs

- `docs/guides/npx-quickstart.md` (prerequisites, first run, data home layout, flags, upgrade/uninstall).
- README / README.ja: add a "Quick start with npx" section next to the clone instructions.

## Out of scope

- Windows support (launcher assumes a POSIX shell environment like the rest of `bin/`).
- Scheduled runs (launchd/cron) from the npx install — stays a clone-mode feature for now.
