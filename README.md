# My World Briefing — Personal Market Intelligence Agent

Automatically collects geopolitical events, stock market moves, and key themes every morning, then delivers a 3-minute brief to Discord and Notion — contextualized to your own portfolio.

---

## Concept

> Not a tool that *outputs* information — an agent that *interprets* it through your own lens.

Bloomberg and NewsPicks surface raw data. This agent ties every event to your holdings, themes, and geopolitical risks, and generates "what this means for you" every day.

---

## Architecture

```bash
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
skills/                # Claude Code custom skills — see skills/README.md
```

See [skills/](skills/README.md) for custom Claude Code skills bundled with this repo.

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

### Interactive Q&A on today's briefing

```bash
bin/chat.sh                # today's briefing (new or resumed session)
bin/chat.sh 2026-05-16    # specific past briefing
bin/chat.sh --list         # list all saved sessions
```

Opens an interactive Claude session with the briefing loaded as context.
On the first run a session UUID is generated and saved to `output/briefing/.sessions/<date>`.
On subsequent runs for the same date the previous conversation is automatically resumed
via `--session-id`, so the full Q&A history carries over between restarts.

Exits with an error if the briefing file for the specified date does not exist.
Session files are stored inside `output/` which is already git-ignored.

### Dry-run (validate credentials without executing)

```bash
.venv/bin/python bin/briefing.py --dry-run
.venv/bin/python bin/xss_intel.py --dry-run
```

Prints a WARNING for each missing credential and exits without calling Claude or any API.

---

## Scheduled Execution (macOS launchd)

See [docs/launchd-setup.md](docs/launchd-setup.md) for the full setup guide (plist template, dry-run validation, register/trigger/unload commands).

---

## Briefing Evaluation

A separate pipeline scores past briefings to measure how well their views held up. It extracts
macro, theme-level views from each briefing, judges them against *later* briefings as ground truth,
and aggregates hit rates into a Mermaid scorecard. LLM calls go through the same `claude` CLI path
(subscription auth) — no extra API key required.

```bash
# 1. Extract structured themes from briefings (all dates; already-extracted ones are skipped)
apps/python/bin/evaluate.sh extract
apps/python/bin/evaluate.sh extract 2026-06-15   # single date

# 2. Score themes whose verification window is covered by later briefings
apps/python/bin/evaluate.sh score

# 3. Build the aggregate report
apps/python/bin/evaluate.sh report
```

Outputs (all under git-ignored `output/`):

- `output/eval/claims/<date>.json` — extracted themes (`direction`, `targets`, `horizon_days`, `type`)
- `output/eval/scores/<date>.json` — verdicts (`hit` / `miss` / `partial` / `unresolved`)
- `output/eval/report.md` — Mermaid `pie` + `xychart-beta` scorecard (hit rate by type / sector / time)

A theme stays `unresolved` until at least one briefing exists inside its window `(date, date + horizon_days]`;
re-running `score` only re-evaluates `unresolved` entries and never overwrites finalized verdicts.
Design notes: [docs/superpowers/specs/2026-06-17-briefing-eval-foundation-design.md](docs/superpowers/specs/2026-06-17-briefing-eval-foundation-design.md).

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

```markdown
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

## Local LLM (experimental)

Optional fully-local RAG over this repository, powered by Ollama + Chroma. The existing Claude Code / briefing / XSS agents are unaffected.

### Prerequisites

```bash
brew install ollama       # or follow https://ollama.com
ollama serve &
ollama pull qwen2.5:14b   # for --briefing: reliable tool calling (~8.5GB RAM with Q4)
ollama pull qwen2.5:7b    # for --ask / --index: smaller, fits the RAG path
ollama pull bge-m3        # embedding model (#135): stronger JP + code retrieval than nomic-embed-text

# optional alternatives — see the Model options table below
ollama pull qwen2.5-coder:14b  # code-heavy --ask queries
ollama pull qwen2.5:32b        # deepest explanations / final synthesis (~20GB RAM)
```

The default generation model is `qwen2.5:14b` for more stable instruction-following and citation quality in the `--briefing` path. If you only run `--ask` / `--index`, override with `LOCAL_LLM_MODEL=qwen2.5:7b`.

#### Model options

Swap the generation model without code edits via `LOCAL_LLM_MODEL` (env) or `--model` (CLI flag). RAM figures are approximate for Q4 quantization; leave headroom for the embedding model and OS.

| Model | Approx. RAM (Q4) | Best for | Trade-offs |
|---|---|---|---|
| `qwen2.5:7b` | ~5 GB | `--ask` / `--index` on the RAG path | Fastest; weaker tool calling, so less reliable for `--briefing` web_search |
| `qwen2.5-coder:14b` | ~9 GB | Code-heavy `--ask` queries over this repo | Stronger on code, but tuned less for general JP briefing prose |
| `qwen2.5:14b` (default) | ~8.5 GB | `--briefing`: reliable tool calling + citation quality | Balanced; fits comfortably on 24 GB RAM with 16K ctx |
| `qwen2.5:32b` | ~20 GB | Deepest explanations / final synthesis stage | Slow; tight on 24 GB RAM — close other apps |

```bash
LOCAL_LLM_MODEL=qwen2.5:32b bin/local_llm.sh --ask "..."   # one-off override
bin/local_llm.sh --briefing --model qwen2.5:7b             # per-invocation flag
```

#### Dual-model briefing (reasoning final stage)

For `--briefing`, the final synthesis stage (自分への示唆 / insight) can run on a
stronger reasoning model while the cheaper main model handles the
extraction/summary stages (#171). Set `LOCAL_LLM_SYNTHESIS_MODEL`:

```bash
LOCAL_LLM_MODEL=qwen2.5:14b \
LOCAL_LLM_SYNTHESIS_MODEL=qwen2.5:32b \
  bin/local_llm.sh --briefing
```

When unset, the synthesis stage uses `LOCAL_LLM_MODEL`, so behavior is unchanged.
On 24 GB RAM, Ollama swaps models between stages — keep the two models within the
memory budget (e.g. 14b + 32b run sequentially, not concurrently).

> **Switching embed models requires a rebuild.** `bge-m3` (1024 dim) and the legacy `nomic-embed-text` (768 dim) produce incompatible vectors. If you change `LOCAL_LLM_EMBED_MODEL` (or are upgrading from a pre-#135 index), the CLI refuses with an `EmbedModelMismatch` error — rebuild with `bin/local_llm.sh --index --reset`.

### Usage

```bash
bin/local_llm.sh --index                       # index ~/work/ai-agent into Chroma
bin/local_llm.sh --status                      # show indexed chunk count & models
bin/local_llm.sh --ask "認証はどう動く？"
bin/local_llm.sh --sources "認証はどう動く？"  # retrieval-only debug
bin/local_llm.sh --index --reset               # rebuild from scratch
bin/local_llm.sh --briefing                    # generate daily briefing locally (saves local_<date>.md)
bin/local_llm.sh --briefing --notion           # ...and post to Notion alongside the Claude version
```

Chroma data is stored in `apps/python/.chroma_db/` (gitignored).

Override defaults via env: `LOCAL_LLM_MODEL`, `LOCAL_LLM_SYNTHESIS_MODEL`, `LOCAL_LLM_EMBED_MODEL`, `LOCAL_LLM_TOP_K`, `LOCAL_LLM_CHROMA_PATH`, `OLLAMA_HOST`.

`--briefing` requires `BRAVE_API_KEY` in `.env` (Free-plan key at https://api-dashboard.search.brave.com/ — see `.env.example`). The CLI pre-fetches Brave Search results for all portfolio tickers, macro news, and geopolitical topics, then injects them as context before local generation; without the key the command exits with an error. Tracked under [#142](https://github.com/KazusaNakagawa/ai-agent-cli/issues/142) (initial offline version) and [#144](https://github.com/KazusaNakagawa/ai-agent-cli/issues/144) (Brave Search integration).

Tracked under [#140](https://github.com/KazusaNakagawa/ai-agent/issues/140) (Epic [#139](https://github.com/KazusaNakagawa/ai-agent/issues/139)). Quality improvements (#135 bge-m3, #136 reranker, #138 AST chunking, #137 generation model) ship as follow-up PRs.

---

## License

MIT
