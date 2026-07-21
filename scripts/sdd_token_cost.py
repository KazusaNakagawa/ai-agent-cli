#!/usr/bin/env python3
"""
Prototype: aggregate token usage/cost for an SDD run from a Claude Code
transcript JSONL file.

Sums the orchestrator's own message usage (deduped by message id) plus
every completed Agent (subagent) tool result's usage/totalTokens, broken
down by resolvedModel.

Usage:
    python3 scripts/sdd_token_cost.py <path-to-transcript.jsonl>

See docs/superpowers/proposals/sdd-token-cost-tracking.md for context.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_rates import RATES, usage_cost  # noqa: E402,F401


def main(path: str) -> None:
    orchestrator_seen_ids: set[str] = set()
    orchestrator_usage = defaultdict(lambda: defaultdict(int))
    orchestrator_model = "claude-sonnet-5"  # default; overwritten if seen

    subagents = []  # (description, agentType, resolvedModel, totalTokens, cost, durationMs)

    with open(path) as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"  [warn] skipping malformed JSON at {path}:{lineno}: {e}",
                    file=sys.stderr,
                )
                continue

            msg = d.get("message")
            if isinstance(msg, dict) and "usage" in msg and not d.get("isSidechain"):
                mid = msg.get("id")
                if mid and mid not in orchestrator_seen_ids:
                    orchestrator_seen_ids.add(mid)
                    u = msg["usage"]
                    for k in (
                        "input_tokens",
                        "output_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                    ):
                        orchestrator_usage[msg.get("model", orchestrator_model)][k] += u.get(k, 0)

            if d.get("type") == "user":
                tur = d.get("toolUseResult")
                if isinstance(tur, dict) and tur.get("status") == "completed" and "usage" in tur:
                    model = tur.get("resolvedModel", "unknown")
                    cost = usage_cost(tur["usage"], model)
                    subagents.append(
                        (
                            tur.get("agentType", "?"),
                            model,
                            tur.get("totalTokens", 0),
                            cost,
                            tur.get("totalDurationMs", 0),
                        )
                    )

    print(f"# SDD token/cost report: {path}\n")

    print("## Orchestrator (main session)")
    orch_total_cost = 0.0
    orch_total_tokens = 0
    for model, u in orchestrator_usage.items():
        cost = usage_cost(u, model)
        orch_total_cost += cost
        tokens = sum(u.values())
        orch_total_tokens += tokens
        print(f"  {model}: {tokens:,} tokens, ${cost:.4f}")
        print(f"    {dict(u)}")
    print(f"  TOTAL: {orch_total_tokens:,} tokens, ${orch_total_cost:.4f}\n")

    print(f"## Subagents ({len(subagents)} calls)")
    sub_total_cost = 0.0
    sub_total_tokens = 0
    by_model = defaultdict(lambda: [0, 0.0, 0])  # tokens, cost, count
    for agent_type, model, tokens, cost, duration_ms in subagents:
        sub_total_cost += cost
        sub_total_tokens += tokens
        by_model[model][0] += tokens
        by_model[model][1] += cost
        by_model[model][2] += 1
        print(
            f"  {agent_type:20s} {model:20s} {tokens:>8,} tok  ${cost:.4f}  {duration_ms/1000:.1f}s"
        )
    print()
    print("  By model:")
    for model, (tokens, cost, count) in by_model.items():
        print(f"    {model}: {count} calls, {tokens:,} tokens, ${cost:.4f}")
    print(f"  TOTAL: {sub_total_tokens:,} tokens, ${sub_total_cost:.4f}\n")

    grand_tokens = orch_total_tokens + sub_total_tokens
    grand_cost = orch_total_cost + sub_total_cost
    print(f"## Grand total: {grand_tokens:,} tokens, ${grand_cost:.4f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <transcript.jsonl>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
