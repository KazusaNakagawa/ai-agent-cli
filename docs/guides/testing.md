# Testing

## Python (`apps/python`)

```bash
cd apps/python
.venv/bin/pytest -v                              # all tests
.venv/bin/pytest tests/test_claude_runner.py -v  # specific module
```

### Supported Python versions

The supported range is **3.11–3.13**, declared as `requires-python` in
`apps/python/pyproject.toml`. `.github/workflows/pytest.yml` runs the whole
suite once per version through a `strategy.matrix`, with `fail-fast: false` so
one failing version does not mask the others. The matrix legs report as
`pytest (3.11)`…`pytest (3.13)`; a separate `test` job aggregates them into the
single required status check that `dev` protects.

`tests/test_python_version_support.py` fails if the declared range, the CI
matrix and the versions named in `README.md` / `README.ja.md` ever disagree — so
widening or narrowing support means changing `requires-python` and the matrix
together, not just the prose.

To reproduce another leg locally:

```bash
uv venv --python 3.11 .venv-311
uv pip sync requirements.txt --python .venv-311/bin/python
.venv-311/bin/pytest -v
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
uv pip compile requirements.in --universal --python-version 3.11 -o requirements.txt
uv pip sync requirements.txt
```

`requirements.txt` is auto-generated — only edit `requirements.in`.

`--universal --python-version 3.11` resolves one lock file that is valid across
the whole supported range instead of only the interpreter that ran the compile.
Without it, the lock omits the backports the older legs need (`backports.tarfile`
for `keyring` on 3.11, `tomli`, `zipp`) and those CI legs fail on import.
