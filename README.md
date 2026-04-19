# My World Briefing — Personal Market Intelligence Agent

Automatically collects geopolitical events, stock market moves, and key themes every morning, then delivers a 3-minute brief to Discord and Notion — contextualized to your own portfolio.

---

## Concept

> Not a tool that *outputs* information — an agent that *interprets* it through your own lens.

Bloomberg and NewsPicks surface raw data. This agent ties every event to your holdings, themes, and geopolitical risks, and generates "what this means for you" every day.

---

## Architecture

```
bin/run.sh
  ├── bin/briefing.py
  │     └── src/handler.py
  │           ├── src/fetcher/stocks.py        # Previous-day % change via yfinance
  │           ├── src/generator/briefing.py    # Builds prompts, calls run_claude() in parallel
  │           │     └── prompts/briefing.md    # Prompt template
  │           ├── src/notifier/discord.py
  │           └── src/notifier/notion.py
  └── bin/xss_intel.py
        └── src/xss_handler.py
              ├── src/generator/xss_report.py  # Builds prompt, calls run_claude()
              │     └── prompts/xss_intel.md
              ├── src/notifier/discord.py
              └── src/notifier/notion.py

src/claude_runner.py   # Shared claude CLI helper (subprocess + WebSearch)
config/
  briefing.json        # Portfolio, watch sectors (14 sectors), geopolitical risks
  xss_intel.json       # XSS target frameworks / libraries / keywords
src/config.py          # JSON → dataclass schema
```

### Key Design Decisions

- **No NewsAPI** — Claude Code CLI's built-in WebSearch handles real-time search
- **No Anthropic API billing** — reuses Claude Code CLI's OAuth authentication; `ANTHROPIC_API_KEY` is explicitly excluded from the subprocess environment to prevent accidental API charges
- **Geopolitical → stock causality** is baked into every daily output
- **watch_sectors** (14 sectors, ~90 tickers) give Claude full market coverage to surface sector moves
- **Degraded mode** — if the sector sweep fails, the main analysis is still delivered

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) installed
- [Claude Code CLI](https://claude.ai/code) installed and authenticated (`claude` in PATH)
- Discord Bot created (Send Messages permission granted)
- Notion integration created with database access

### Install

```bash
git clone https://github.com/KazusaNakagawa/ai-agent-cli.git
cd ai-agent-cli

uv venv .venv
uv pip sync requirements.txt
```

### Environment Variables

```bash
cp .env.example .env
# Edit .env
```

| Variable | Source | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | Discord Developer Portal | Bot authentication |
| `CHANNEL_ID` | Right-click channel → Copy ID | Target channel |
| `NOTION_API_KEY` | Notion integrations page | API authentication |
| `NOTION_DATABASE_ID` | Database URL | Target database |

### Run

```bash
bin/run.sh
```

---

## Scheduling (macOS launchd)

The agents can be scheduled to run automatically every morning using macOS launchd.

```bash
# Install and register the launchd job (runs at 08:00 daily)
bash launchd/install.sh

# Verify registration
launchctl list | grep aiagent

# Run immediately (for testing)
launchctl kickstart -k gui/$(id -u)/com.aiagent.run

# Uninstall
bash launchd/uninstall.sh
```

To ensure the Mac wakes from sleep before the 08:00 trigger:

```bash
sudo pmset repeat wake MTWRFSU 07:55:00
```

Logs are written to `log/launchd.stdout.log` and `log/launchd.stderr.log`.

---

## Configuration

### `config/briefing.json`

All monitoring targets are managed here — no code changes needed.

```json
{
  "portfolio": {
    "tickers": ["PLTR", "NVDA"],
    "themes": ["AI regulation", "US-China relations", "semiconductors"]
  },
  "watch_sectors": [
    {
      "sector": "AI & Cloud",
      "tickers": ["NVDA", "MSFT", "GOOGL", "META", "AMZN"],
      "notes": "AI capex cycle, model competition, and regulation are the main drivers"
    }
  ],
  "geopolitical": {
    "conflicts": [
      {
        "name": "Russia-Ukraine War",
        "affected_sectors": ["Energy", "Defense", "Grains"],
        "related_tickers": ["LMT", "RTX", "XOM"],
        "notes": "NATO defense spending increase is a tailwind for LMT/RTX"
      }
    ]
  }
}
```

### `prompts/briefing.md`

Prompt template for the briefing agent. Variables: `{tickers}` `{themes}` `{geopolitical}` `{watch_sectors}` `{stocks}`. Edit this file to change Claude's output behavior.

---

## Testing

```bash
# Run all tests
.venv/bin/pytest -v

# Run a specific module
.venv/bin/pytest tests/test_claude_runner.py -v
```

| Test file | Coverage |
|---|---|
| `test_claude_runner.py` | `run_claude()` — CLI discovery, timeout, error handling, env masking |
| `test_generator_briefing.py` | Context builders, parallel execution, degraded mode |
| `test_config.py` | `load_config()` validation (watch_sectors, tickers) |

---

## Sample Output

```
## Today's Summary (1 sentence)
...

## Why It Moved (Story)
...geopolitics, sentiment, supply/demand in 3–4 lines...

## Geopolitical → Market Causality
...how each risk translated to sector/ticker moves today...

## Sector Movements (All Sectors)
- AI & Cloud: NVDA 10-day winning streak (+18%)...
- Energy (Oil & Gas): Brent $128 on Hormuz closure...
...

## What This Means for You
...1–2 lines for portfolio holders...

## Sources
- Article title — outlet (URL)
```

---

## Dependency Management

```bash
# After adding a package to requirements.in
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
```

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Local manual run | ✅ Done |
| 2 | Discord delivery | ✅ Done |
| 3 | Notion delivery | ✅ Done |
| 4 | macOS launchd daily scheduler | ✅ Done |
| 5 | Unit tests (pytest) | ✅ Done |
| 6 | AWS Lambda + EventBridge automation | 📋 Planned |
| 7 | DynamoDB for dynamic config | 📋 Planned |

---

## License

MIT
