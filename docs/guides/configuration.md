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
| `NOTION_DATABASE_ID_JOURNAL` | Database URL | Target database for Journal ↔ Notion sync (separate from `NOTION_DATABASE_ID`) |
| `BRAVE_API_KEY` | [api-dashboard.search.brave.com](https://api-dashboard.search.brave.com/) | Local LLM briefing web search |

### Credential Management

Lookup priority: **OS Keychain → `.env` (fallback)**

#### A. Register via Keychain (recommended)

```bash
cd apps/python
.venv/bin/python -c "
from src.credentials import set_credential
set_credential('NOTION_API_KEY', 'ntn_xxx...')
set_credential('NOTION_DATABASE_ID', 'xxx...')
set_credential('NOTION_DATABASE_ID_JOURNAL', 'xxx...')
"
```

Verify registration:

```bash
security find-generic-password -s "ai-agent" -a "NOTION_API_KEY" -w
```

#### B. Use `.env` (fallback when keychain is not set)

```bash
cp .env.example .env
# Fill in NOTION_API_KEY and other variables
```

Place `.env` at the repository root (`/work/ai-agent/.env`). `apps/python/.env` is not read.

### Troubleshooting: 401 Unauthorized (Notion)

Steps to investigate `API token is invalid`:

1. **Check which token is actually being used**

   ```bash
   # Keychain value (takes priority)
   security find-generic-password -s "ai-agent" -a "NOTION_API_KEY" -w

   # .env value
   grep NOTION_API_KEY /path/to/ai-agent/.env
   ```

2. **Compare against the Notion dashboard**

   Go to `https://www.notion.so/my-integrations` → select your integration → click **Show** and compare with the value above.

3. **Update the keychain if they differ**

   ```bash
   cd apps/python
   .venv/bin/python -c "from src.credentials import set_credential; set_credential('NOTION_API_KEY', 'new_token_here')"
   ```

   > Editing `.env` has no effect while an old value exists in the keychain — the keychain always wins.

4. **Verify the integration is connected to the database**

   If the token is correct but 401 persists, the integration may not have access to the target database.
   Open the database in Notion → `…` → **Add connections** → select your integration.
