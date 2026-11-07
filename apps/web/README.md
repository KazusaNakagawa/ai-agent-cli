# apps/web

Next.js 14 (App Router) + Tailwind + shadcn/ui frontend for ai-agent.
Sibling of `apps/python/` (FastAPI backend) in the ai-agent monorepo.

## Scripts

```bash
npm install
npm run dev      # next dev — http://localhost:3000
npm run build    # production build (also runs type-check)
npm run start    # serve the production build
npm run lint     # next lint
npm run test     # vitest run (one-off)
npm run test:watch
npm run test:e2e # playwright — e2e smoke gate (uses ports 3000 / 8000)
npm run test:e2e:isolated  # same suite from a temp copy on 3100 / 8100, beside your dev servers
```

## API client

`lib/api.ts` exports `apiFetch(path, init)` which:

1. Reads `apps/web/.token` on every call (no caching — tokens can rotate).
2. Sets `Authorization: Bearer <token>`.
3. Prefixes `path` with `API_BASE` (default `http://127.0.0.1:8000`).

Both `.token` location and `API_BASE` are overridable via env:

| Env var | Default | Purpose |
|---|---|---|
| `API_BASE` | `http://127.0.0.1:8000` | FastAPI backend origin |
| `AI_AGENT_TOKEN_PATH` | `<cwd>/.token` | Bearer token file (server-side reads only) |

The FastAPI side generates the token at `~/.ai-agent/session-token` on first boot;
`bin/serve.sh` is responsible for mirroring it to `apps/web/.token` (gitignored).

`apiFetch` uses `node:fs`, so it must only be called from server contexts
(Server Components, Route Handlers, Server Actions). Importing it from a client
component will fail at build time.

## Tests

Vitest + jsdom + Testing Library. Tests live in `tests/` and run with
`npm run test`. See `tests/smoke.test.tsx` for the baseline pattern.

### E2E smoke gate

`npm run test:e2e` runs the Playwright specs in `e2e/`.

- `onboarding-and-run.spec.ts` starts with the first-time flow: launch → 4-step onboarding wizard → `POST /api/run?dry_run=true` → sidebar reachable. It then covers re-running and skipping setup, and the chat and journal paths, with their backends mocked in the browser.
- `workspace.spec.ts` covers the file workspace.

Vitest covers the rest. Treat the suite as the manual smoke gate before cutting a release. It is **not** wired into the `web` GitHub Actions workflow, because Playwright's browser download (~150 MB) inflates CI time disproportionately.

The tests in `onboarding-and-run.spec.ts` run serially and share backend state: the first test marks onboarding done, and the chat tests depend on it. Run the whole file. A chat test picked alone with `-g` lands on the wizard and fails.

Isolation is per-run, no manual cleanup required:

- `playwright.config.ts` wipes `e2e/.tmp-home/` and pre-seeds a session
  token there before either server boots.
- FastAPI is started with `HOME=<tmp-home>` and
  `BRIEFING_CONFIG_PATH=<tmp-home>/.ai-agent/briefing.json`, so
  `state.json`, the session token, and `briefing.json` all live under the
  tmp tree — your real `~/.ai-agent/` is untouched.
- Step 3 is submitted blank, so no `PUT /api/credentials/*` calls reach
  the macOS Keychain.
- The job runs with `dry_run=true`, so no claude / Discord / Notion calls
  happen.

Failures drop a screenshot + trace under `e2e/test-results/`; view a
trace with `npx playwright show-trace e2e/test-results/<test>/trace.zip`.

Prerequisites (one-time per machine):

```bash
cd apps/python
uv venv .venv                  # create the venv the config invokes
uv pip sync requirements.txt   # install backend deps
cd ../web
npx playwright install chromium
```

The config invokes `apps/python/.venv/bin/uvicorn` directly, so the venv
must exist before `npm run test:e2e` is run.

#### Running beside your dev servers

`npm run test:e2e` starts its own `next dev` on 3000 and FastAPI on 8000, and refuses to reuse running ones. `npm run test:e2e:isolated` (`scripts/e2e-isolated.mjs`) runs the same suite without stopping yours:

- It copies `apps/web` and `apps/python` into a temp directory and starts both servers there, on 3100 and 8100. A second `next dev` in this checkout would share `.next` with the running one, hence the copy.
- The copy is the git-visible file set: tracked files with your uncommitted edits, plus new files not yet added. Gitignored personal config, `input/`, `output/`, and tokens stay behind.
- `node_modules` and `.venv` are symlinked from this checkout, so install them first.
- Arguments after `--` go to Playwright, e.g. `npm run test:e2e:isolated -- e2e/workspace.spec.ts`.
- To change the ports, set `E2E_WEB_PORT` / `E2E_API_PORT`. The script stops before copying anything if a port is taken.
- A passing run deletes the copy. A failed run keeps it and prints its path, so the report and traces stay readable. `E2E_ISOLATED_KEEP=1` keeps it either way.
- An interrupted run (Ctrl+C) also leaves the copy behind; its path is printed when the run starts.

## References

- Phase 1 design spec: `.claude/superpowers/specs/2026-05-29-web-ui-phase1-design.md`
  (gitignored — local only)
- Backend setup: `docs/guides/web-ui-setup.md`
