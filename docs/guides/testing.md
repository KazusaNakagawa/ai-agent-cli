# Testing

```bash
cd apps/python
.venv/bin/pytest -v                              # all tests
.venv/bin/pytest tests/test_claude_runner.py -v  # specific module
```

| Test file | Coverage |
|---|---|
| `test_claude_runner.py` | `run_claude()` — CLI discovery, timeout, error handling, env masking |
| `test_generator_briefing.py` | Context builders, parallel execution, degraded mode |
| `test_config.py` | `load_config()` validation (watch_sectors, tickers) |
| `test_notion.py` | Notion page creation, markdown→block conversion |

## Dependency management

```bash
# After adding a package to requirements.in
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
```

`requirements.txt` is auto-generated — only edit `requirements.in`.
