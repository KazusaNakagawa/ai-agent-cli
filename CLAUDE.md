# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Setup, architecture, configuration, and testing details are documented in [README.md](README.md).

## Quick Commands

```bash
uv pip sync requirements.txt   # Install deps
bin/run.sh                     # Run both agents
.venv/bin/pytest -v            # Run tests
uv pip compile requirements.in -o requirements.txt  # Recompile deps
```

## Key Implementation Notes

- **`src/claude_runner.py`** is the single entry point for all claude CLI calls. Always use `run_claude()` — never call `subprocess.run(["claude", ...])` directly elsewhere.
- **`ANTHROPIC_API_KEY` must not reach the subprocess** — it is stripped in `run_claude()`. If you add new subprocess calls to claude, apply the same env filter.
- **`requirements.txt` is auto-generated** — only edit `requirements.in`, then recompile.
- **`CONFIG = load_config()`** runs at import time in `src/config.py`. Tests that call `load_config()` directly must patch `src.config.CONFIG_PATH`.

## Git Conventions

Branch naming: `feat/` `fix/` `refactor/` `docs/` `chore/`

Commit format ([Conventional Commits](https://www.conventionalcommits.org/)):
```
<type>: <short summary in English>
```

PR: title matches commit format (under 70 chars); body has bullet summary + test plan checklist.
