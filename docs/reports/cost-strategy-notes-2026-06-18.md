# Cost Strategy Notes (2026-06-18)

Ideas for reducing exposure if Claude usage ever shifts from flat-rate
subscription (Pro/Max) billing to per-token API billing. None of this is
urgent while on a subscription plan — it's a checklist to revisit if pricing
changes.

## 1. Abstract the model invocation

Keep the model ID switchable via environment variable / config
(`CLAUDE_MODEL`, `briefing.json`'s `model` field — see
[`src.claude_runner.get_model()`](../../apps/python/src/claude_runner.py)) so
swapping "Opus → Sonnet → local LLM" stays cheap regardless of pricing
changes. This also hedges against single-model dependency risk in general.

## 2. Use today's high-performance models as a "teacher"

Under usage-based billing, hitting a full-performance model every call gets
expensive. While still on a subscription, build out briefing-generation and
report-creation logic with a high-performance model, then lock in its output
patterns as prompt templates, skills, and few-shot examples — that makes it
easier to preserve quality later even after swapping in cheaper models
(Haiku-class or local Ollama).

## 3. Partially migrate to local RAG / Ollama

The experimental [local LLM mode](../features/local-llm.md) (Ollama + Chroma)
already covers deterministic work — formatting ticker data, posting to
Notion/Discord. Shifting that class of task off the API, while keeping
genuinely reasoning-heavy work (geopolitical analysis, portfolio-impact
assessment) on Claude, keeps the per-unit cost impact down if billing changes.

## 4. Make usage visible

`scripts/token_usage_report.py` / `/api/usage/monitor` already log token
usage per task. Keep that data flowing so cost impact can be estimated ahead
of any pricing change, and to prioritize what to optimize first.
