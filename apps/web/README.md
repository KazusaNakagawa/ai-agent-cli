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

## References

- Phase 1 design spec: `.claude/superpowers/specs/2026-05-29-web-ui-phase1-design.md`
  (gitignored — local only)
- Backend setup: `docs/web-ui-setup.md`
