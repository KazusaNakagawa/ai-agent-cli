# Configuration

## `config/briefing.json`

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

## `prompts/briefing.md`

Prompt template for the briefing agent. Variables: `{tickers}` `{themes}` `{geopolitical}` `{watch_sectors}` `{stocks}`. Edit this file to change Claude's output behavior.

## Environment Variables

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
| `BRAVE_API_KEY` | [api-dashboard.search.brave.com](https://api-dashboard.search.brave.com/) | Local LLM briefing web search |
