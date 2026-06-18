# Briefing Evaluation

A separate pipeline scores past briefings to measure how well their views held up. It extracts
macro, theme-level views from each briefing, judges them against *later* briefings as ground truth,
and aggregates hit rates into a Mermaid scorecard. LLM calls go through the same `claude` CLI path
(subscription auth) — no extra API key required.

## Usage

```bash
# 1. Extract structured themes from briefings (all dates; already-extracted ones are skipped)
apps/python/bin/evaluate.sh extract
apps/python/bin/evaluate.sh extract 2026-06-15   # single date

# 2. Score themes whose verification window is covered by later briefings
apps/python/bin/evaluate.sh score

# 3. Build the aggregate report
apps/python/bin/evaluate.sh report
```

## Outputs

All under git-ignored `output/`:

| Path | Content |
|---|---|
| `output/eval/claims/<date>.json` | Extracted themes (`direction`, `targets`, `horizon_days`, `type`) |
| `output/eval/scores/<date>.json` | Verdicts (`hit` / `miss` / `partial` / `unresolved`) |
| `output/eval/report.md` | Mermaid `pie` + `xychart-beta` scorecard (hit rate by type / sector / time) |

A theme stays `unresolved` until at least one briefing exists inside its window `(date, date + horizon_days]`; re-running `score` only re-evaluates `unresolved` entries and never overwrites finalized verdicts.

Design notes: [docs/superpowers/specs/2026-06-17-briefing-eval-foundation-design.md](superpowers/specs/2026-06-17-briefing-eval-foundation-design.md).
