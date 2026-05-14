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

### Dry-run (validate credentials without executing)

```bash
.venv/bin/python bin/briefing.py --dry-run
.venv/bin/python bin/xss_intel.py --dry-run
```

Prints a WARNING for each missing credential and exits without calling Claude or any API.

---

## Scheduled Execution (macOS launchd)

macOS uses **launchd** instead of cron. `bin/run.sh` sources `.env` automatically so API credentials are available in non-interactive shells.

**Schedule behaviour:**

| Day | What runs |
|---|---|
| Mon – Thu | `briefing.py` (daily market briefing) |
| Fri | `briefing.py` → `weekly_summary.py` (daily + weekly recap) |

### 1. Validate credentials first (dry-run)

```bash
cd /path/to/ai-agent
source .env
.venv/bin/python bin/briefing.py --dry-run
```

No WARNING lines → credentials are set correctly.

### 2. Create the plist

Save the following to `~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kazusa.ai-agent-briefing</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/ai-agent/bin/run.sh</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/YOUR_USERNAME</string>
    </dict>

    <!-- Mon–Fri 07:00 -->
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>/path/to/ai-agent/log/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/ai-agent/log/launchd.stderr.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Replace `/path/to/ai-agent` and `YOUR_USERNAME` with your actual values.

### 3. Register and verify

```bash
# Register
launchctl load ~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist

# Confirm registered (shows "-  0  com.kazusa.ai-agent-briefing")
launchctl list | grep kazusa

# Test trigger immediately
launchctl start com.kazusa.ai-agent-briefing

# Watch logs
tail -f /path/to/ai-agent/log/launchd.stderr.log
```

### 4. Unregister (if needed)

```bash
launchctl unload ~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist
```

### Requirements

| Item | Why |
|---|---|
| `.env` at project root | `bin/run.sh` sources it for API tokens |
| `~/.claude/` accessible | Claude Code CLI reads its OAuth token from here |
| `log/` directory exists | Output target for launchd stdout/stderr |
| `/opt/homebrew/bin` in PATH | Required for `claude` CLI installed via Homebrew |

```bash
mkdir -p /path/to/ai-agent/log
```

If credentials are missing at runtime, the agent logs a WARNING per missing credential and writes output to `output/briefing_YYYY-MM-DD.md` instead of sending to Discord/Notion.

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
| 4 | Unit tests (pytest) | ✅ Done |
| 5 | AWS Lambda + EventBridge automation | 📋 Planned |
| 6 | DynamoDB for dynamic config | 📋 Planned |

---

## License

MIT
