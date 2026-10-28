# Jev experiments

Ad hoc scripts for evaluating `typesafe-ai/jev` (TypeSafe AI's System One model)
through Vercel AI Gateway. Not part of the briefing pipeline — kept here so the
setup does not have to be rediscovered.

Jev returns typed values with calibrated probabilities instead of text. It answers
`boolean` (P(true)), `choice` (one option plus a distribution) and `score`
(fractional position over ordered levels) questions about one shared state.

## Setup

```bash
cd scripts/jev
npm install
```

Every Node script needs `AI_GATEWAY_API_KEY` (create one with
`vercel ai-gateway api-keys create`). To keep it out of shell history, read it
per run instead of exporting it:

```bash
read -s "AI_GATEWAY_API_KEY?key: " && AI_GATEWAY_API_KEY=$AI_GATEWAY_API_KEY node <script>.mjs
```

(`read -s "VAR?prompt"` is zsh syntax; in bash use `read -s -p "key: " AI_GATEWAY_API_KEY`.)

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
| `results.mjs` | Shared helper: writes each run to `results/<script>-<timestamp>.json`. |

## Reproducing the experiments

Each Node script prints a summary and saves the full run (answers,
probabilities, latency, usage) to `results/<script>-<UTC timestamp>.json`.
Runs never overwrite each other, so two runs of the same input can be diffed.
`job.json`, `money-job.json` and `results/` hold briefing bodies and ledger
rows, so they are gitignored and stay local.

### 1. Smoke test

```bash
node try-jev.mjs
```

Expect one answer per type (`marketMoving` P(true), `category` choice,
`confidence` score) in about a second for well under $0.0001.

### 2. eval-judge comparison

Needs the briefing and evaluator output under `apps/python/output/`
(or `$BRIEF_LENS_HOME/output/`).

```bash
# from the repo root
python3 scripts/jev/make_job.py 20            # seed 42: same 20 claims every time
cd scripts/jev
node compare.mjs 5 30                         # 5 claims, 30 s apart
```

`compare.mjs [limit] [delaySeconds]` retries each call up to 5 times. Expect
most calls to fail with `GatewayRateLimitError` while Jev is in early access:
about one success every 5 minutes was observed regardless of pacing.

### 3. Household-ledger classification

Needs the ledger imported with `bin/money.sh` (`apps/python/output/money/`).

```bash
# from the repo root
apps/python/.venv/bin/python scripts/jev/make_money_job.py
cd scripts/jev
node money.mjs
```

One request classifies every distinct description, so it does not hit the
capacity limit. `expected` comes from the categories `config/money_rules.json`
assigns now; rows no rule matches are marked `??` for a human to judge.

The recorded runs used the rules before the human answers were added as rules
(13 rule-labeled rows, 5 uncategorized). Re-running today labels all rows,
including `cash_withdrawal`, which is not among the choices `money.mjs` offers,
so that row always counts as a miss. Probabilities also vary between runs by up
to about ±0.2, so per-row numbers will not match exactly.

## Known constraint

Jev caps a request at 64,000 tokens total, 32,000 for the state plus the longest
question. The eval-judge task feeds joined follow-up briefings whose median size
is around 76,000 characters. Japanese text measured 0.699 tokens per character,
so the state fits roughly 45,750 characters and about 90% of the real workload
does not fit. `job.json` truncates the follow-up text, which means any agreement
rate measured this way is not directly comparable to the full-context baseline.
