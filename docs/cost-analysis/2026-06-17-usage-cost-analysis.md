# Usage Cost Analysis — 2026-06-16 / 06-17

Source logs:
- `apps/python/log/usage/20260616-usage.jsonl`
- `apps/python/log/usage/20260617-usage.jsonl`

## What these logs measure

These are **Claude-model costs**, not local-LLM costs. The records are emitted by
the Claude briefing agent: `src/generator/briefing.py` runs the `メイン分析` and
`セクタースイープ` prompts via `run_claude`, and `claude_runner._parse_and_log_usage`
writes the claude CLI's `total_cost_usd` through `src/usage_logger.py`. Every
`run_claude` call with a label is logged, so Claude cost aggregation **is already
implemented**.

The local-LLM (Ollama) briefing path is separate and free, so it produces no
cost records.

## Results

| Date | Runs | Cost |
|---|---|---|
| 2026-06-16 | 2 | $1.977 |
| 2026-06-17 | 2 | $1.931 |
| **Total** | **4** | **$3.908** (avg $0.977/run) |

| Job | Runs | Avg cost | Avg duration |
|---|---|---|---|
| メイン分析 (main analysis) | 2 | $0.911 | ~84s |
| セクタースイープ (sector sweep) | 2 | $1.043 | ~120s |

## Projection (at the observed 2 runs/day pace)

- Daily ~$1.95 → Monthly ~$59 → Annual ~$713

## Cost structure — what actually drives it

Of 805K total tokens:

| Token type | Share | Volume | Notes |
|---|---|---|---|
| cache_read | 55.2% | 445K | Highest volume, cheapest unit price. Caching is working — healthy. |
| cache_creation | 40.4% | 325K (~81K/run) | The cost driver. |
| output | 2.5% | 20K | Smallest volume, highest unit price. |
| input | <2% | 15K | Negligible. |

**The cache_creation is NOT our prompt content.** Our own prompt assets are tiny:
`briefing.md` ~232 tokens, `briefing_sectors.md` ~109, the few-shot example ~215
(~550 tokens total). The ~81K cache_creation/run is the **Claude Code CLI's own
system prompt + tool definitions** (web_search etc.), which are written to the
prompt cache on first use and then re-read (the 445K cache_read confirms this).
So trimming our prompts or article context would barely move the cost.

## Real levers (Claude path)

Because our prompt content is already small, the meaningful options are
structural, not prompt-size tuning:

1. **Migrate the briefing to the local-LLM path** (free). Already the strategy in
   epic #139 / #198. The reasoning-model and clustering work (#169/#170/#171)
   make the local path capable enough to take over.
2. **Reduce claude CLI invocation count.** The briefing fires two parallel
   `run_claude` calls (main + sectors); each pays the CLI system-prompt
   cache_creation. Merging them would pay that overhead once.
3. **Call the API with a cheaper model** instead of the claude CLI, avoiding the
   CLI's large system-prompt/tool overhead entirely for batch generation.

## Note on a discarded countermeasure

An earlier attempt (PR #203, closed) tuned the local-LLM pre-fetch article budget.
That was mistargeted: it touches the free Ollama path, not the Claude path these
logs measure, so it does not reduce the analyzed cost. Recorded here so the dead
end is not re-tried.

## Caveats

- Sample is only 2 days / 4 runs. Good for trend; the monthly figure assumes the
  current pace continues.
- `cost_usd` is the claude CLI `total_cost_usd` as-is, so it may include
  web_search tool charges. Back-calculating from token unit prices lands between
  Sonnet and Opus, consistent with tool cost being folded in.
