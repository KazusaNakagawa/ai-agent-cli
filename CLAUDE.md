# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Setup, architecture, configuration, and testing details are documented in [README.md](README.md).
> Custom Claude Code skills used in this project: [.claude/skills/](.claude/skills/README.md).

## Layout

Python sources live under `apps/python/`. Root-level `bin/run.sh` and `bin/chat.sh` are thin wrappers that `exec` into `apps/python/bin/` for backward compatibility.

## Quick Commands

```bash
# From apps/python/
cd apps/python
uv pip sync requirements.txt   # Install deps
.venv/bin/pytest -v            # Run tests
uv pip compile requirements.in -o requirements.txt  # Recompile deps

# From repo root
bin/run.sh                     # Run both agents (delegates to apps/python/bin/run.sh)
bin/chat.sh                    # Launch chat session
```

## Key Implementation Notes

- **`apps/python/src/claude_runner.py`** is the single entry point for all claude CLI calls. Always use `run_claude()` — never call `subprocess.run(["claude", ...])` directly elsewhere.
- **`ANTHROPIC_API_KEY` must not reach the subprocess** — it is stripped in `run_claude()`. If you add new subprocess calls to claude, apply the same env filter.
- **`apps/python/requirements.txt` is auto-generated** — only edit `requirements.in`, then recompile.
- **`CONFIG = load_config()`** runs at import time in `apps/python/src/config.py`. Tests that call `load_config()` directly must patch `src.config.CONFIG_PATH`.

## Config File Rules

| File | Purpose | Git |
|---|---|---|
| `apps/python/config/briefing.json` | Real batch execution config (personal data) | Ignored |
| `apps/python/config/briefing.json.example` | Schema documentation and template | Tracked |
| `apps/python/tests/config/briefing.json` | Fixture config for CI and local tests | Tracked |

- **`apps/python/config/briefing.json` is never committed.** It holds personal portfolio data used only at runtime.
- **CI and local `pytest` always load `apps/python/tests/config/briefing.json`** — `apps/python/tests/conftest.py` sets `BRIEFING_CONFIG_PATH` before any import of `src.config`, so no `cp` step is needed in CI.
- **When adding or changing config schema** (new fields, renamed keys), update both `apps/python/config/briefing.json.example` and `apps/python/tests/config/briefing.json` to keep them in sync.
- **`apps/python/config/briefing.json`** must be updated manually by the operator after any schema change.

## Git Conventions

Branch naming: `feat/` `fix/` `refactor/` `docs/` `chore/`

Commit format ([Conventional Commits](https://www.conventionalcommits.org/)):
```
<type>: <short summary in English>
```

PR: title matches commit format (under 70 chars); body has bullet summary + test plan checklist.
