# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Running

```bash
# Create venv and install dependencies
uv venv .venv
uv pip sync requirements.txt

# Run both agents sequentially
bin/run.sh

# Run individually
source .venv/bin/activate
python bin/briefing.py
python bin/xss_intel.py

# Run tests
.venv/bin/pytest -v
```

## Dependency Management

`requirements.in` is the manually managed direct-dependency file. Never edit `requirements.txt` directly — it is auto-generated.

```bash
# After adding a package to requirements.in
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
```

## Architecture

Two independent agents share the same Discord/Notion notifiers and a common claude CLI helper.

### Shared Claude CLI Helper (`src/claude_runner.py`)

All claude CLI invocations go through `run_claude()`:

```python
run_claude(prompt: str, label: str, timeout: int = 300) -> str
```

- Finds `claude` binary via `shutil.which`
- Excludes `ANTHROPIC_API_KEY` from the subprocess environment — forces WebSearch to use OAuth (subscription) auth instead of API billing
- Sets `stdin=subprocess.DEVNULL` to prevent the CLI from waiting for terminal input
- Handles timeout (`subprocess.TimeoutExpired`) and non-zero exit codes with structured logging
- Truncates error messages to 2000 chars to avoid embedding large stdout in exceptions

### Briefing Agent

```
bin/briefing.py
  └── src/handler.py
        ├── src/fetcher/stocks.py        # Fetches previous-day % change via yfinance
        ├── src/generator/briefing.py    # Builds prompts; calls run_claude() in parallel (ThreadPoolExecutor)
        │     └── prompts/briefing.md    # Template vars: {tickers} {themes} {geopolitical} {stocks}
        │     └── prompts/briefing_sectors.md  # Template vars: {watch_sectors} {stocks}
        ├── src/notifier/discord.py
        └── src/notifier/notion.py
```

Parallel execution: main analysis (`_TIMEOUT_MAIN=300s`) and sector sweep (`_TIMEOUT_SECTORS=480s`) run concurrently. If only the sector sweep fails, the agent falls back to degraded mode (main analysis only).

### XSS Intel Agent

```
bin/xss_intel.py
  └── src/xss_handler.py
        ├── src/generator/xss_report.py  # Builds prompt; calls run_claude()
        │     └── prompts/xss_intel.md
        ├── src/notifier/discord.py
        └── src/notifier/notion.py
```

### Config Schema (`src/config.py`)

- `BriefingConfig` holds `PortfolioConfig` + `GeopoliticalConfig` + `list[WatchSector]`
- `XssIntelConfig` holds `XssTargetsConfig` (frameworks / libraries / keywords)
- `CONFIG = load_config()` runs at module import time (module-level singleton)
- `get_xss_config()` is a lazy singleton — loaded only on first access

### Config Files (`config/`)

- `briefing.json` — manages `portfolio` (tickers/themes), `watch_sectors` (14 sectors), and `geopolitical.conflicts`. Change monitoring targets here without touching code.
- `xss_intel.json` — manages `targets` (frameworks/libraries/keywords)

### Prompt Templates (`prompts/`)

`render()` in `src/generator/prompt.py` loads `prompts/{name}.md` and expands it via `str.format(**kwargs)`. To modify prompt behavior, edit only the `.md` file.

## Environment Variables (`.env`)

| Variable | Purpose |
|---|---|
| `DISCORD_TOKEN` | Discord Bot authentication |
| `CHANNEL_ID` | Target Discord channel |
| `NOTION_API_KEY` | Notion API authentication |
| `NOTION_DATABASE_ID` | Target Notion database |

> `ANTHROPIC_API_KEY` — if present in `.env`, it is intentionally stripped from the subprocess environment before calling the claude CLI to prevent API charges.

## Logging

`log/{YYYYMMDD}-app.log` — DEBUG level. Console output is INFO level. Obtain loggers via `get_logger()` in `src/logger.py`.

## Testing

```bash
.venv/bin/pytest -v
```

| File | What it tests |
|---|---|
| `tests/test_claude_runner.py` | `run_claude()` — subprocess mocking, env masking, error truncation |
| `tests/test_generator_briefing.py` | Context builders, parallel execution, degraded mode |
| `tests/test_config.py` | `load_config()` validation |

## Git Conventions

### Branch Naming

```
feature/<short-description>   # New features
fix/<short-description>       # Bug fixes
refactor/<short-description>  # Refactoring with no behavior change
docs/<short-description>      # Documentation only
```

### Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short summary in English>

[optional body]
```

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change with no behavior change |
| `docs` | Documentation only |
| `chore` | Tooling, deps, config (no production code) |

### Pull Request

- **Title**: `<type>: <short summary>` — same format as commit (under 70 chars)
- **Body**: bullet-point summary + test plan checklist
- One logical change per PR; squash unrelated fixups before opening
