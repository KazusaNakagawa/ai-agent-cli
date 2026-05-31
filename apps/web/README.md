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
npm run test:e2e # playwright — onboarding-and-run smoke gate
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

`npm run test:e2e` runs the single Playwright scenario in `e2e/` that walks
the first-time user flow end-to-end: launch → 4-step onboarding wizard →
`POST /api/run?dry_run=true` → sidebar reachable. This is intentionally
the *only* E2E test — everything else is covered by Vitest. Treat it as
the manual smoke gate before cutting a release; it is **not** wired into
the `web` GitHub Actions workflow because Playwright's browser download
(~150 MB) inflates CI time disproportionately for a single scenario.

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

Prerequisites: `cd apps/python && uv pip sync requirements.txt` (the
config invokes `apps/python/.venv/bin/uvicorn`) and one-time
`npx playwright install chromium`.

## References

- Phase 1 design spec: `.claude/superpowers/specs/2026-05-29-web-ui-phase1-design.md`
  (gitignored — local only)
- Backend setup: `docs/web-ui-setup.md`
