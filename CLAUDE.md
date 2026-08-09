# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Project overview and user-facing docs: [README.md](README.md) and [docs/](docs/).
> Custom Claude Code skills: [.claude/skills/](.claude/skills/README.md).

## Layout

Python sources live under `apps/python/`. Root-level `bin/run.sh` and `bin/chat.sh` are thin wrappers that `exec` into `apps/python/bin/` for backward compatibility.

## Quick Commands

```bash
# From apps/python/
uv venv .venv                  # Create venv (first time only)
uv pip sync requirements.txt   # Install deps
.venv/bin/pytest -v            # Run tests
uv pip compile requirements.in -o requirements.txt  # Recompile deps

# From repo root
bin/run.sh    # Run both agents
bin/chat.sh   # Launch chat session
```

## Key Implementation Notes

- **`apps/python/src/claude_runner.py`** is the single entry point for all claude CLI calls. Always use `run_claude()` — never call `subprocess.run(["claude", ...])` directly elsewhere.
- **Subprocess env handling for `ANTHROPIC_API_KEY` is mode-dependent.** `run_claude()` calls `_build_env(auth_mode)` based on `state.read_state().auth_mode` (defaults to `"cli"`):
  - `cli`: the key is **stripped** so the claude CLI uses its OAuth session.
  - `api`: the key from `credentials.get_credential("ANTHROPIC_API_KEY")` (Keychain → `.env` fallback) is **injected** into the subprocess env.

  Route new subprocess calls to claude through `_build_env(state.read_state().auth_mode)`. Never set `ANTHROPIC_API_KEY` directly in the subprocess env outside this helper.
- **`apps/python/requirements.txt` is auto-generated** — only edit `requirements.in`, then recompile.
- **`src.config.CONFIG` is lazy.** A module-level `__getattr__` calls `load_config()` on first attribute access — importing `src.config` does **not** read `briefing.json`. Tests that call `load_config()` directly must patch `src.config.CONFIG_PATH`.

## Config File Rules

| File | Purpose | Git |
|---|---|---|
| `apps/python/config/briefing.json` | Real batch execution config (personal data) | Ignored |
| `apps/python/config/briefing.json.example` | Schema documentation and template | Tracked |
| `apps/python/tests/config/briefing.json` | Fixture config for CI and local tests | Tracked |
| `apps/python/config/self_agent_profile.md` | self-agent's persistent persona profile (personal data) | Ignored |
| `apps/python/config/self_agent_profile.md.example` | Schema documentation and template | Tracked |
| `apps/python/config/holdings.json` | Portfolio positions for `bin/portfolio.sh` (personal data) | Ignored |
| `apps/python/config/holdings.json.example` | Schema documentation and template | Tracked |

- `apps/python/config/briefing.json` and `holdings.json` are **never committed**.
- CI and local `pytest` always load `apps/python/tests/config/briefing.json` — `conftest.py` sets `BRIEFING_CONFIG_PATH` before any import of `src.config`.
- When adding or changing config schema, update both `.example` and `tests/config/briefing.json`.

## UI Verification

- When fixing or changing a screen in `apps/web`, verify the behavior in a real browser via Playwright (`apps/web/e2e/`, or an ad hoc script run from `apps/web` with `node script.mjs` using `@playwright/test`'s `chromium`) instead of relying on code reading alone. Reproduce the reported issue first, then confirm the fix removes it.

## Code Style

- **Code comments and docstrings must be written in English** (both Python and TypeScript), unified across the codebase. User-facing chat responses stay in Japanese, but in-code documentation is English only — do not mix languages within a file.

## Git Conventions

Branch naming: `feature/` `fix/` `refactor/` `docs/` `chore/`

Branch flow: `dev` is the working branch. Feature branches fork from `dev`, and PRs target `dev` as base. `main` is synced only via `dev` → `main` PRs.

Commit format ([Conventional Commits](https://www.conventionalcommits.org/)):
```
<type>: <short summary in English>
```

PR: title matches commit format (under 70 chars); body has bullet summary + test plan checklist.
