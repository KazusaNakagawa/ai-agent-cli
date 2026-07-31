# Testing

## Python (`apps/python`)

```bash
cd apps/python
.venv/bin/pytest -v                              # all tests
.venv/bin/pytest tests/test_claude_runner.py -v  # specific module
```

`conftest.py` sets `BRIEFING_CONFIG_PATH` to `apps/python/tests/config/briefing.json`
before any import of `src.config`, so tests never read the personal
`config/briefing.json`.

| Test file | Coverage |
|---|---|
| `test_claude_runner.py` | `run_claude()` — CLI discovery, timeout, error handling, env masking |
| `test_generator_briefing.py` | Context builders, parallel execution, degraded mode |
| `test_config.py` | `load_config()` validation (watch_sectors, tickers) |
| `test_notion.py` | Notion page creation, markdown→block conversion |
| `test_api_usage_monitor.py` | `/api/usage/monitor` — aggregation, date filters, response cache |

## Web (`apps/web`)

```bash
cd apps/web
npm test              # vitest run — component and store unit tests
npm run test:watch    # vitest in watch mode
npm run test:e2e      # playwright (e2e/) — boots its own FastAPI + Next.js
npm run lint          # next lint
```

The Playwright config launches both servers itself with `HOME` pointed at a
throwaway tmp dir, so `~/.ai-agent` (state.json, session token) and the personal
`briefing.json` are never touched by an e2e run.

Per `CLAUDE.md`, screen changes are verified in a real browser via Playwright —
reproduce the reported issue first, then confirm the fix removes it.

## Dependency management

```bash
# After adding a package to requirements.in
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
```

`requirements.txt` is auto-generated — only edit `requirements.in`.
