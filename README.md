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
  │           ├── src/generator/briefing.py    # Invokes claude CLI (WebSearch)
  │           │     └── prompts/briefing.md    # Prompt template
  │           ├── src/notifier/discord.py
  │           └── src/notifier/notion.py
  └── bin/xss_intel.py
        └── src/xss_handler.py
              ├── src/generator/xss_report.py  # Invokes claude CLI (WebSearch)
              │     └── prompts/xss_intel.md
              ├── src/notifier/discord.py
              └── src/notifier/notion.py

config/
  briefing.json   # Portfolio, watch sectors (14 sectors), geopolitical risks
  xss_intel.json  # XSS target frameworks / libraries / keywords
src/config.py     # JSON → dataclass schema
```

### Key Design Decisions

- **No NewsAPI** — Claude Code CLI's WebSearch handles real-time search
- **No Anthropic API key needed (local)** — reuses Claude Code CLI authentication
- **Geopolitical → stock causality** is baked into every daily output
- **watch_sectors** (14 sectors, ~90 tickers) give Claude full market coverage to surface sector moves

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) installed
- [Claude Code CLI](https://claude.ai/code) installed and authenticated
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
| 4 | AWS Lambda + EventBridge automation | 🔜 Next |
| 5 | DynamoDB for dynamic config | 📋 Planned |

---

## License

MIT
