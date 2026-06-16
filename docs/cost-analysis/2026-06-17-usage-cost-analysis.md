# Usage Cost Analysis — 2026-06-16 / 06-17

Source logs:
- `apps/python/log/usage/20260616-usage.jsonl`
- `apps/python/log/usage/20260617-usage.jsonl`

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

## Cost structure

Of 805K total tokens:

| Token type | Share | Volume | Notes |
|---|---|---|---|
| cache_read | 55.2% | 445K | Highest volume, cheapest unit price. Cache is working — healthy. |
| cache_creation | 40.4% | 325K (~81K/run) | **The real cost driver.** Each run re-writes the pre-fetched article bodies + system prompt to cache (~12.5x the read unit price). |
| output | 2.5% | 20K | Smallest volume but highest unit price (~$75/Mtok class). |
| input | <2% | 15K | Negligible. |

## Levers (aligned with `docs/tips.md`)

1. **Reduce cache_creation (highest ROI).** Summarize/trim the pre-fetch context (full article-body injection) before building the prompt so cache-write tokens drop directly. 81K/run is large.
2. **Cache TTL / shared prefix.** If メイン分析 and セクタースイープ share the system prompt / common context, align the common prefix so cache_creation is paid once instead of per job.
3. **Move deterministic work local** (tips.md option 3). Shifting the formatting parts of the sector sweep to a local LLM / rules would directly cut the most expensive $1.04/run job.

## Caveats

- Sample is only 2 days / 4 runs. Good for trend, but the monthly figure assumes the current pace continues.
- `cost_usd` is the claude CLI `total_cost_usd` recorded as-is, so it may include web_search tool charges. Back-calculating from token unit prices lands between Sonnet and Opus, consistent with tool cost being folded in.

## Decision

Proceeding with lever #1 — reduce cache_creation by trimming the injected pre-fetch context.

## Implemented countermeasure

The pre-fetch injection budget is now configurable via env (defaults unchanged, so behavior is preserved until tuned):

| Env | Default | Effect |
|---|---|---|
| `LOCAL_LLM_ARTICLE_MAX_CHARS` | `1800` | Body cap per article |
| `LOCAL_LLM_ARTICLE_PER_MACRO` | `2` | Macro articles injected |
| `LOCAL_LLM_ARTICLE_PER_GROUP` | `1` | Articles per ticker/geo/event |

Suggested lower-cost preset to A/B against quality (then compare the next day's
`log/usage/*.jsonl`):

```bash
LOCAL_LLM_ARTICLE_MAX_CHARS=1200 LOCAL_LLM_ARTICLE_PER_MACRO=1 bin/local_llm.sh --briefing
```

Rough expectation: macro 2→1 articles and 1800→1200 chars cuts the injected
body volume by ~40–50%, which (since article bodies dominate cache_creation)
should meaningfully lower the ~81K cache_creation tokens/run. Validate
empirically against the logged cost before adopting as the default.
