# My World Briefing — Personal Market Intelligence Agent

Automatically collects geopolitical events, stock market moves, and key themes every morning, then delivers a 3-minute brief to Discord and Notion — contextualized to your own portfolio.

---

## Concept

> Not a tool that *outputs* information — an agent that *interprets* it through your own lens.

Bloomberg and NewsPicks surface raw data. This agent ties every event to your holdings, themes, and geopolitical risks, and generates "what this means for you" every day.

---

## Architecture

```
bin/run.sh → apps/python/bin/run.sh
  ├── python -m src.handler              # Daily market briefing
  │     ├── src/fetcher/stocks.py        # Previous-day % change via yfinance
  │     ├── src/generator/briefing.py    # Builds prompts, calls run_claude() in parallel
  │     ├── src/notifier/discord.py
  │     └── src/notifier/notion.py
  ├── python -m src.weekly_handler       # Fridays only: weekly recap
  └── python -m src.xss_handler          # XSS intel agent — currently disabled in run.sh
        ├── src/generator/xss_report.py
        ├── src/notifier/discord.py
        └── src/notifier/notion.py

src/claude_runner.py   # Shared claude CLI helper (subprocess + WebSearch)
config/briefing.json   # Portfolio, watch sectors, geopolitical risks
```

**Key design decisions**

- No NewsAPI — Claude Code CLI's built-in WebSearch handles real-time search
- No per-token Anthropic API billing — runs on the Claude Code CLI OAuth session, which requires an active paid Claude subscription (Pro/Max); the free plan cannot run this
- Geopolitical → stock causality is baked into every daily output
- Degraded mode — if the sector sweep fails, the main analysis is still delivered

---

## Setup

**Prerequisites:** Python 3.11+, [uv](https://github.com/astral-sh/uv), [Claude Code CLI](https://claude.ai/code) authenticated, Discord Bot, Notion integration.

```bash
git clone https://github.com/KazusaNakagawa/ai-agent-cli.git
cd ai-agent-cli
uv venv .venv
uv pip sync requirements.txt
cp .env.example .env   # add DISCORD_TOKEN, NOTION_API_KEY, etc.
```

See [docs/configuration.md](docs/configuration.md) for all environment variables and config schema.

## Run

```bash
bin/run.sh             # daily briefing (+ weekly recap on Fridays)

# Interactive Q&A on today's briefing
bin/chat.sh            # new or resumed session
bin/chat.sh 2026-05-16 # specific past briefing
bin/chat.sh --list     # list saved sessions

# Dry-run (validate credentials without executing)
cd apps/python
.venv/bin/python -m src.handler --dry-run
.venv/bin/python -m src.xss_handler --dry-run
```

### Batch scripts (`bin/`)

Thin wrappers that `exec` into `apps/python/bin/`. Each targets a specific task:

| Script | Purpose |
|---|---|
| `run.sh` | Run the daily briefing (+ weekly recap on Fri) — see [Architecture](#architecture) for the disabled XSS intel agent |
| `chat.sh` | Interactive Q&A on a briefing session |
| `serve.sh` | Launch the Web UI (uvicorn); `PORT` overridable |
| `briefing_api.sh` | Generate a briefing via the API entry point |
| `chart.sh` | Generate charts (e.g. stock price comparison) |
| `gen_wordset.sh` | Generate word-set JSON (Stage 1) |
| `evaluate.sh` | Run the briefing evaluation pipeline |
| `eval_report.sh` | Extract → score → report evaluation results |
| `local_llm.sh` | Local LLM mode (Ollama + Chroma) |
| `archive.sh` | Archive a month's briefings to Google Drive via rclone |

---

## Docs

| Topic | Link |
|---|---|
| Configuration (env vars, config schema, prompts) | [docs/configuration.md](docs/configuration.md) |
| Scheduled execution (macOS launchd) | [docs/launchd-setup.md](docs/launchd-setup.md) |
| Briefing archive (monthly zip → Google Drive via rclone) | [docs/briefing-archive.md](docs/briefing-archive.md) |
| Briefing evaluation pipeline | [docs/evaluation.md](docs/evaluation.md) |
| Local LLM mode (Ollama + Chroma) | [docs/local-llm.md](docs/local-llm.md) |
| Testing & dependency management | [docs/testing.md](docs/testing.md) |
| Web UI setup | [docs/web-ui-setup.md](docs/web-ui-setup.md) |

---

## License

MIT
