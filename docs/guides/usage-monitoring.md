# Usage Monitoring — Monitor tab and Settings > Usage

Two independent views of token usage and cost. They read **different files**
and are never merged, so their numbers are expected to differ.

| View | Data source | Scope | Written by |
|---|---|---|---|
| **Monitor** (`/monitor`) | `~/.claude/projects/**/*.jsonl` | Every Claude Code session on this machine — all repos, all interactive work | The `claude` CLI itself |
| **Settings > Usage** (`/config/usage`) | `apps/python/log/usage/YYYYMMDD-usage.jsonl` | This app's own runs only (briefing, chat, self-agent) | [`src/usage_logger.py`](../../apps/python/src/usage_logger.py) |

All costs on both screens are **API-equivalent estimates**. Usage runs on a
Claude Pro/Max subscription, so the dollar figures are a "what this would have
cost on the API" yardstick, not a bill.

Treat them as a rough guide — good enough to see scale and spot a spike, not
good enough to reconcile against anything. Three known gaps, surfaced in the UI
under *Why the numbers are approximate* and printed by the CLI report:

- **Rates are hand-maintained** from published pricing. There is no pricing API,
  so an upstream change lands here late — see [Drift detection](#2b-drift-detection--scriptscheck_model_ratespy).
- **Server-side tool use is not counted.** Web search bills `$0.01` per request
  on top of tokens and never reaches the total.
- **Cache writes with no recorded TTL** fall back to the cheaper 5-minute rate,
  so those entries read low.

## Monitor: where the data comes from

Nothing is stored locally for the Monitor tab. Each request re-scans the
transcripts and the result lives only in memory.

```
~/.claude/projects/<project>/<session>.jsonl   (written by the claude CLI)
        │
        │  src/usage_monitor.py :: aggregate(root, since, until)
        ▼
  Report(by_project, by_date, by_model, by_date_model, unpriced_models)
        │
        │  GET /api/usage/monitor  (FastAPI, 60s in-process cache)
        ▼
  Next.js proxy  app/api/[...path]/route.ts   (injects the Bearer token,
        │                                      Cache-Control: no-store)
        ▼
  MonitorDashboard.tsx  →  React useState  →  MonitorStackedChart
```

### 1. Aggregation — [`apps/python/src/usage_monitor.py`](../../apps/python/src/usage_monitor.py)

- Root is `DEFAULT_ROOT = ~/.claude/projects`. A missing root yields an empty
  report rather than an error.
- Walks every `*.jsonl` under the root and keeps lines that carry a
  `message.usage` object.
- **Deduped by `message.id`** across all files, so a session resumed across
  process restarts (which produces several JSONL files) is counted once. Lines
  without an id are counted per line.
- Tokens = `input_tokens + output_tokens + cache_creation_input_tokens +
  cache_read_input_tokens`.
- The bucket date is the message timestamp converted to **local time**, so a
  late-night session lands on the day you experienced it, not the UTC day.
- `since` / `until` are inclusive `YYYY-MM-DD` filters applied to that local date.
- Buckets are produced per project, per date, per model, and per (date, model)
  for the stacked chart.

### 2. Pricing — [`apps/python/src/claude_rates.py`](../../apps/python/src/claude_rates.py)

The rates live in [`apps/python/config/model_rates.json`](../../apps/python/config/model_rates.json)
— tracked in git, unlike the personal-data configs — and `claude_rates.RATES`
loads them into a dict of **exact** model id →
`(input, output, cache_write_5m, cache_write_1h, cache_read)` USD per 1M tokens.
Matching is exact on purpose — substring matching mis-maps as model ids evolve.
Every field is required per model: a partially specified model is rejected
rather than defaulted, because a silent `0` for one component is the failure the
file exists to prevent. A model missing from the table costs `$0` and is
surfaced in the response as `unpriced_models`, which the UI renders as an amber
warning line.

**Rates cannot be fetched automatically.** The Models API
(`client.models.list()` / `.retrieve()`) returns `id`, `display_name`,
`created_at`, `max_input_tokens`, `max_tokens` and `capabilities` — there is no
price field, and no other pricing endpoint exists. The table is therefore
hand-maintained, and [`scripts/check_model_rates.py`](../../scripts/check_model_rates.py)
is what stops that from failing silently.

Cache writes are billed by TTL: a 1-hour write costs **2x** input where a
5-minute write costs 1.25x. `usage_cost()` splits
`cache_creation_input_tokens` using the `usage.cache_creation` breakdown that
transcripts carry, taking the 5-minute share as the remainder so an entry with
no breakdown falls back to the cheaper rate instead of being dropped. Claude
Code writes almost entirely 1-hour caches, so ignoring the split understates
the total by roughly 12%.

When a new model appears in that warning, add its id and published rates to
`model_rates.json`. The same table backs the CLI report and
`scripts/sdd_token_cost.py`.

### 2b. Drift detection — [`scripts/check_model_rates.py`](../../scripts/check_model_rates.py)

```bash
python3 scripts/check_model_rates.py                       # default transcript root and table
python3 scripts/check_model_rates.py --transcripts /path --rates /path/rates.json
```

Exits non-zero on either of two findings, so it can gate a scheduled run:

- **Unpriced models** — a model id appears in transcript `message.usage`
  entries with no entry in the table. This is the failure that let
  `claude-opus-5` report `$0` for three weeks. `<synthetic>` is exempt: it is a
  CLI-internal message, not a model call.
- **Rate drift** — Claude Code writes `{"type": "cost-state"}` records carrying
  a per-model `modelUsage` breakdown and the `costUSD` it charged. Recomputing
  that from the table and comparing catches a published price change, a new
  cache tier, or a typo in the config.

The comparison **brackets** rather than equates. `modelUsage` reports one
combined `cacheCreationInputTokens` with no 5-minute/1-hour split, and the two
TTLs are priced differently, so the real cost can land anywhere between an
all-5m and an all-1h reading. A record outside that bracket is drift; one
inside it is consistent with some split.

That bracket is also the blind spot, and worth knowing before trusting a pass:
on a write-heavy record the spread is wide, so a rate error smaller than it goes
unseen. Records with few or no cache writes are where the check has teeth —
there the bracket collapses to a point and a cent of error shows. Records using
web search are skipped entirely: those bill `$0.01` per request on top of
tokens, which the table does not model.

Reconciliation in tests runs against `scripts/tests/fixtures/cost_state.jsonl`,
real records checked into the repo, so CI does not depend on the operator's
local transcripts.

### 3. API — `GET /api/usage/monitor`

Defined in [`apps/python/web/routers/usage.py`](../../apps/python/web/routers/usage.py).
Bearer required, like every endpoint except `/api/health`.

```bash
TOKEN=$(cat ~/.ai-agent/session-token)
curl -H "Authorization: Bearer $TOKEN" \
    "http://127.0.0.1:8000/api/usage/monitor?since=2026-07-01&until=2026-07-31"
```

- `since` / `until` are validated twice: a `^\d{4}-\d{2}-\d{2}$` pattern, then a
  real calendar-date parse (so `2026-13-40` returns 422 instead of silently
  filtering everything out).
- Response: `total_tokens`, `total_cost_usd`, `by_project`, `by_date` (each with
  a nested `models` split), `by_model`, `unpriced_models`. Buckets are sorted by
  cost, descending.
- **Cache**: scanning the whole transcript tree is expensive, so identical
  `(root, since, until)` queries are served from an in-process dict for **60
  seconds**, capped at 32 entries (oldest evicted). It is guarded by a lock
  because `def` endpoints run in FastAPI's threadpool. The cache is process
  memory only — it disappears on restart and is never written to disk.

### 4. Rendering — [`apps/web/components/screens/MonitorDashboard.tsx`](../../apps/web/components/screens/MonitorDashboard.tsx)

- Fetches `/api/usage/monitor` through the Next.js catch-all proxy
  (`app/api/[...path]/route.ts`), which adds the Bearer token server-side so the
  token never reaches the browser.
- The **Range** select (`Last 7 days` / `Last 30 days` / `All time`) is turned
  into a `since` query param by `sinceForRange()` in `lib/monitor-types.ts`;
  changing it re-fetches. The **Metric** select (`Cost (USD)` / `Tokens`) only
  switches between the already-fetched numbers; it does not re-fetch.
- The response is held in React `useState` for the life of the page. There is
  **no `localStorage`, no IndexedDB, and no client-side cache** — a reload
  re-fetches.
- Model colors come from `buildModelColorMap()`, which assigns theme-aware CSS
  custom properties (`--series-1` …) by **sorted model id**, so a model keeps the
  same color across charts and renders.
- A day with no transcript activity is absent from `by_date`. `fillDateGaps()`
  in `lib/monitor-types.ts` re-inserts it as an empty bar before the chart
  renders, so bar position tracks the calendar rather than rank. The expansion
  is capped at 400 days so one very old entry in the **All time** range cannot
  produce thousands of bars.

### CLI equivalent

Same aggregation, no server needed:

```bash
python3 scripts/token_usage_report.py                          # all time, default root
python3 scripts/token_usage_report.py --since 2026-07-01 -v    # date-filtered, per-file trace
python3 scripts/token_usage_report.py /path/to/other/projects  # alternate transcript root
```

## Settings > Usage: this app's own runs

- Every `claude` CLI call made by this app appends one JSONL record (timestamp,
  label, token counts, cost, duration) to
  `apps/python/log/usage/YYYYMMDD-usage.jsonl`.
- Rotation is **opt-in**: `USAGE_LOG_ROTATION_ENABLED` in
  [`src/constants.py`](../../apps/python/src/constants.py) is `False` by default
  (a code constant, not an env var) so the full cost history stays available to
  the dashboard. Logging failures are swallowed — a logging error must never
  break the run that produced it.
- Endpoints: `GET /api/usage/dates` (available days, newest first),
  `GET /api/usage/summary` (per-day totals, oldest first, for the line chart),
  `GET /api/usage?date=YYYYMMDD` (raw records for one day).
- Rendered by `apps/web/components/screens/UsageDashboard.tsx`, reachable both at
  `/config/usage` and from the Settings modal's **Usage** tab.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `No transcript usage found for this range.` | No `message.usage` lines in `~/.claude/projects` for those dates. Widen the range to **All time** to confirm the root is being found at all. |
| `Unpriced models (excluded from cost): …` | The model id is missing from the rate table. Add it to `apps/python/config/model_rates.json` with its published rates, then re-run `scripts/check_model_rates.py`. |
| `<synthetic>` appears as a model | CLI-internal messages, not real model calls. Shown for completeness and labelled as such in the UI. |
| Monitor and Settings > Usage disagree | Expected — different data sources (all Claude Code traffic vs. this app's runs). Neither is wrong. |
| A change in usage does not show up | The API caches identical queries for 60 seconds. Wait, or switch range and back. |
| `Failed to load monitor data: HTTP 401` | The Next.js side cannot read `apps/web/.token`. Restart via `./bin/serve.sh`, which re-mirrors `~/.ai-agent/session-token`. |
