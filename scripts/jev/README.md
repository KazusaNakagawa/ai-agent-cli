# Jev experiments

Ad hoc scripts for evaluating `typesafe-ai/jev` (TypeSafe AI's System One model)
through Vercel AI Gateway. Not part of the briefing pipeline — kept here so the
setup does not have to be rediscovered.

Jev returns typed values with calibrated probabilities instead of text. It answers
`boolean` (P(true)), `choice` (one option plus a distribution) and `score`
(fractional position over ordered levels) questions about one shared state.

## Setup

```bash
npm install                                   # from this directory
export AI_GATEWAY_API_KEY="..."               # vercel ai-gateway api-keys create
```

The gateway requires paid credits: Jev is not in the free-tier model subset, and
a card on file alone is not enough.

## Scripts

| Script | Purpose |
|---|---|
| `try-jev.mjs` | Smoke test. One news item, one question of each answer type. |
| `make_job.py` | Builds `job.json` from `apps/python/output/eval/` and the follow-up briefings (fixed seed, reproducible). |
| `compare.mjs` | Runs the eval-judge verdict question against a `job.json` sample and compares with the baseline verdicts produced by `run_claude`. |
| `make_money_job.py` | Builds `money-job.json` from the household ledger: one row per distinct description, with names, branches and account numbers redacted. |
| `money.mjs` | Classifies every `money-job.json` row in a single request (one `choice` question per row) and scores against the rule categories. |

`compare.mjs` expects `job.json` in this directory: an array of claims carrying
`theme`, `direction`, `targets`, `horizon_days`, `type`, `followups` and
`baseline_verdict`. Generate it with `python3 scripts/jev/make_job.py [sample_size]`
from the repo root.

## Known constraint

Jev caps a request at 64,000 tokens total, 32,000 for the state plus the longest
question. The eval-judge task feeds joined follow-up briefings whose median size
is around 76,000 characters. Japanese text measured 0.699 tokens per character,
so the state fits roughly 45,750 characters and about 90% of the real workload
does not fit. `job.json` truncates the follow-up
text, which means any agreement rate measured this way is not directly
comparable to the full-context baseline.
