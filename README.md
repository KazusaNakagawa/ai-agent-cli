# My World Briefing — Personal Market Intelligence Agent

Automatically collects geopolitical events, stock market moves, and key themes every morning, then delivers a 3-minute brief to Discord and Notion — contextualized to your own portfolio.

---

## Concept

> Not a tool that *outputs* information — an agent that *interprets* it through your own lens.

Bloomberg and NewsPicks surface raw data. This agent ties every event to your holdings, themes, and geopolitical risks, and generates "what this means for you" every day.

---

## Architecture

![Data flow](docs/architecture.png)

<sub>Source: [docs/architecture.drawio](docs/architecture.drawio) — sequence-level detail in [docs/sequence-diagrams.md](docs/sequence-diagrams.md)</sub>

```
bin/*.sh → apps/python/bin/*.sh          # thin wrappers that exec into the Python app

apps/python/
  src/handler.py                  # Daily market briefing (bin/run.sh)
  │     ├── fetcher/stocks.py     # Previous-day % change via yfinance
  │     ├── generator/briefing.py # Builds prompts, calls run_claude() in parallel
  │     ├── notifier/local_md.py  # Writes output/briefing_YYYY-MM-DD.md first
  │     ├── notifier/discord.py
  │     └── notifier/notion.py
  src/weekly_handler.py           # Fridays only: weekly recap + Notion comment ingestion
  src/self_agent_handler.py       # Judgment log → persona profile → Notion (bin/self_agent.sh)
  src/xss_handler.py              # XSS intel agent — currently disabled in run.sh
  src/claude_runner.py            # Shared claude CLI helper (subprocess + WebSearch)
  web/                            # FastAPI backend for the Web UI (localhost + bearer token)
  config/briefing.json            # Portfolio, watch sectors, geopolitical risks

apps/web/                         # Next.js UI — briefing viewer, chat, journal, usage monitor
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
cp .env.example .env      # add DISCORD_TOKEN, NOTION_API_KEY, etc.

cd apps/python
uv venv .venv
uv pip sync requirements.txt

cd ../web && npm install  # only needed for the Web UI
```

See [docs/guides/configuration.md](docs/guides/configuration.md) for all environment variables and config schema.

## Run

```bash
bin/run.sh             # daily briefing (+ weekly recap on Fridays)

# Interactive Q&A on today's briefing
bin/chat.sh            # new or resumed session
bin/chat.sh 2026-05-16 # specific past briefing
bin/chat.sh --list     # list saved sessions

# Web UI — FastAPI (:8000) + Next.js (:3000), opens the browser
bin/serve.sh
bin/serve.sh --no-browser

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
| `serve.sh` | Launch the full Web UI — FastAPI + Next.js; `API_PORT` / `WEB_PORT` overridable |
| `self_agent.sh` | Turn judgment-log entries into a persona profile and post it to Notion |
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
| Configuration (env vars, config schema, prompts) | [docs/guides/configuration.md](docs/guides/configuration.md) |
| Scheduled execution (macOS launchd) | [docs/guides/launchd-setup.md](docs/guides/launchd-setup.md) |
| Scheduled execution (cron + pmset, alternative) | [docs/guides/cron-setup.md](docs/guides/cron-setup.md) |
| Briefing archive (monthly zip → Google Drive via rclone) | [docs/guides/briefing-archive.md](docs/guides/briefing-archive.md) |
| Testing & dependency management | [docs/guides/testing.md](docs/guides/testing.md) |
| Web UI setup | [docs/guides/web-ui-setup.md](docs/guides/web-ui-setup.md) |
| Briefing evaluation pipeline | [docs/features/evaluation.md](docs/features/evaluation.md) |
| Journal ↔ Notion sync | [docs/features/journal-notion-sync.md](docs/features/journal-notion-sync.md) |
| Notion comment → judgment-log ingestion | [docs/features/notion-comment-judgment-ingestion.md](docs/features/notion-comment-judgment-ingestion.md) |
| Local LLM mode (Ollama + Chroma) | [docs/features/local-llm.md](docs/features/local-llm.md) |
| Sequence diagrams (core flows) | [docs/sequence-diagrams.md](docs/sequence-diagrams.md) |
| XSS intel agent (idea, not yet active) | [docs/ideas/xss-vulnerability-detection-agent.md](docs/ideas/xss-vulnerability-detection-agent.md) |
| Reports & audits | [docs/reports/](docs/reports/) |

---

## License

MIT
