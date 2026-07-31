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

`RATES` maps an **exact** model id to `(input, output, cache_write, cache_read)`
USD per 1M tokens. Matching is exact on purpose — substring matching mis-maps as
model ids evolve. A model missing from the table costs `$0` and is surfaced in
the response as `unpriced_models`, which the UI renders as an amber warning line.

When a new model appears in that warning, add its id and published rates to
`RATES`. The same table backs the CLI report and `scripts/sdd_token_cost.py`.

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
| `Unpriced models (excluded from cost): …` | The model id is missing from `RATES`. Add it to `apps/python/src/claude_rates.py` with its published rates. |
| `<synthetic>` appears as a model | CLI-internal messages, not real model calls. Shown for completeness and labelled as such in the UI. |
| Monitor and Settings > Usage disagree | Expected — different data sources (all Claude Code traffic vs. this app's runs). Neither is wrong. |
| A change in usage does not show up | The API caches identical queries for 60 seconds. Wait, or switch range and back. |
| `Failed to load monitor data: HTTP 401` | The Next.js side cannot read `apps/web/.token`. Restart via `./bin/serve.sh`, which re-mirrors `~/.ai-agent/session-token`. |
