# SDD Token Usage Tracking — Proposal

## Background / Motivation

`.superpowers/sdd/` files (`task-N-brief.md` / `task-N-report.md` / `progress.md`) preserve
implementation details and TDD results (RED/GREEN), but **token usage and cost per task are
never recorded**.

While reviewing the execution record for Issue #350 (Journal chat state persistence), we
confirmed all 8 tasks (Task 1–7 + final review) were completed and merged via `progress.md`,
but there was no way to trace how much each task actually cost.

Enterprise usage is subject to monthly/org-wide cost caps. SDD spawns an implementer subagent
and a reviewer subagent per task, so token consumption tends to be significant — full SDD
should be reserved for work with real architectural judgment or high failure cost, not applied
by default. We want to be able to analyze after the fact which interactions or task granularity
drive cost, to inform estimates and cap-management decisions.

## Current Constraints

- The `subagent-driven-development` skill lives under the official `superpowers` plugin, at
  `~/.claude/plugins/cache/claude-plugins-official/superpowers/<version>/skills/...`, which is
  version-managed. Editing it directly would be overwritten on the next plugin update.
- Claude Code's subagent invocation (Agent tool) has no API for the caller session to directly
  retrieve per-agent token usage. Candidate ways to obtain it:
  1. `/cost` command (cumulative for the current session) — could work by diffing before/after
     each task
  2. Claude Code transcript logs (`~/.claude/projects/.../*.jsonl`) — the `usage` field can be
     aggregated retroactively, even for past runs
  3. Apply the pattern already used in this repo, `apps/python/src/usage_logger.py` (records
     `total_cost_usd` from claude CLI calls to JSONL), to SDD task execution as well

## Proposed Recording Format

Append aggregated figures to each task line in `progress.md`, and keep a breakdown in each
`task-N-report.md`.

### `progress.md` extension

```
Task 1: complete (commits e4e6e99..4aafa2b, review clean)
  tokens: implementer 42,300 / reviewer 18,900 / total 61,200 (est. $0.31)
```

### `task-N-report.md` extension (append at the end)

```markdown
## Token Usage

| Role | Input | Output | Cache read | Cache write | Cost (USD) |
|---|---|---|---|---|---|
| Implementer | 12,400 | 3,800 | 26,000 | 100 | $0.18 |
| Reviewer | 8,200 | 1,600 | 9,000 | 0 | $0.09 |
| **Total** | | | | | **$0.27** |
```

Aggregation would pull `message.usage.{input_tokens,output_tokens,cache_read_input_tokens,
cache_creation_input_tokens}` from the corresponding session in
`~/.claude/projects/<project>/*.jsonl`, and convert to USD using a per-model rate table
(Sonnet/Opus/Haiku).

## Implementation Options

| Option | Description | Pros | Cons |
|---|---|---|---|
| A. Extend the skill itself | Add an instruction to each step of `subagent-driven-development` to record usage on task completion, and upstream it as a PR to the superpowers plugin | Standardized, benefits every project | We can't edit it directly; depends on upstream acceptance |
| B. Local wrapper skill | Add a thin wrapper (e.g. `sdd-with-cost`) under this repo's `.claude/skills/` that runs an aggregation script after SDD completes | Can implement immediately, self-contained in this repo | Separate from the SDD skill itself, needs to be invoked deliberately |
| C. Post-hoc aggregation script only | Build a CLI that parses transcript logs against the commit range/timestamps in `.superpowers/sdd/progress.md`, independent of when it's run | Doesn't touch the SDD skill (plugin-managed) at all; can be applied retroactively to past records like #350 | Not real-time; depends on transcript retention period |

**Recommendation: C first, then B once validated.** Rationale:
- Option C can start without touching the plugin-managed SDD skill, and can be applied
  immediately to the Issue #350 execution record to get real measured numbers. Verifying
  "does this actually give the precision needed for cap management" should come before
  building anything more permanent.
- Once precision and workflow are validated, promote to Option B (local wrapper skill) so
  recording happens automatically as part of routine use.

## Next Actions

1. ~~Inspect the `usage` field structure in the transcript JSONL and build a prototype
   aggregation script~~ — done, see `scripts/sdd_token_cost.py`.
2. ~~Run a trial aggregation against the Issue #350 SDD execution and compute the actual
   cost~~ — done. Results below.
3. Decide whether to proceed to Option B (local wrapper skill) based on whether the precision
   is good enough for practical use.

### Trial results (Issue #350, 2026-07-08 orchestrator session)

```
$ python3 scripts/sdd_token_cost.py <orchestrator-transcript>.jsonl

Orchestrator (main session): 22.0M tokens, $9.25 (claude-sonnet-5)
Subagents (16 calls: 8x implementer + 8x reviewer, claude-haiku-4-5): 740K tokens, $0.19
Grand total: 22.7M tokens, $9.44
```

Key finding: **the orchestrator session itself accounts for ~98% of the cost**, not the
subagents. This flips the original assumption in this proposal's Background section — SDD's
per-task implementer/reviewer subagent pattern is not the main cost driver here; the
orchestrator's own context (which grows as it reads every brief/report and holds the full
plan across all tasks) is. Any cost-cap mitigation should target orchestrator context growth
(e.g. summarizing completed task reports instead of keeping them in-context) rather than
subagent count/model choice.

Caveats on the numbers above:
- `claude-fable-5` usage appeared in the orchestrator's own model mix with no rate-table
  entry (script prints a warning and reports $0 for it) — the $9.25 orchestrator figure is a
  floor, not exact.
- Pricing in `RATES` is a manually maintained snapshot (2026-07); it will drift and needs a
  periodic refresh, ideally sourced from the same place `apps/python/src/usage_logger.py`
  gets its rates.
- The script currently targets a single transcript file. Tasks that resumed the session
  across process restarts (new session id) would need multi-file aggregation.

## References

- Existing similar implementation: `apps/python/src/usage_logger.py` (records `total_cost_usd`
  from claude CLI calls to JSONL)
- Output format reference: `docs/cost-analysis/2026-06-17-usage-cost-analysis.md`
