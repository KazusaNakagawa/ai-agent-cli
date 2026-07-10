"""Shared per-model pricing table for Claude token cost estimation.

Used by scripts/token_usage_report.py and scripts/sdd_token_cost.py so the
rates are maintained in one place.
"""

from __future__ import annotations

import sys

# USD per 1M tokens: (input, output, cache_write, cache_read)
# Source: published Anthropic API pricing as of 2026-07.
# Keyed by exact model id; add new ids here as models are released rather
# than relying on substring matching, which can mis-map as model names
# evolve (e.g. a future id containing "claude-sonnet-5" as a substring but
# priced differently).
RATES = {
    "claude-sonnet-5": (3.00, 15.00, 3.75, 0.30),
    "claude-opus-4-8": (15.00, 75.00, 18.75, 1.50),
    "claude-haiku-4-5": (0.80, 4.00, 1.00, 0.08),
    "claude-fable-5": (10.00, 50.00, 12.50, 1.00),
    "claude-sonnet-4-6": (3.00, 15.00, 3.75, 0.30),
}

_unpriced_models_warned: set[str] = set()


def rate_for(model: str) -> tuple[float, float, float, float]:
    """Return the rate tuple for a model, warning once per unknown model."""
    if model in RATES:
        return RATES[model]
    if model not in _unpriced_models_warned:
        _unpriced_models_warned.add(model)
        print(
            f"  [warn] no rate table entry for model '{model}' — cost shown as $0",
            file=sys.stderr,
        )
    return (0.0, 0.0, 0.0, 0.0)


def usage_cost(usage: dict, model: str) -> float:
    """Estimate USD cost for one usage dict under the given model's rates."""
    in_rate, out_rate, cw_rate, cr_rate = rate_for(model)
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    return (
        inp * in_rate + out * out_rate + cw * cw_rate + cr * cr_rate
    ) / 1_000_000
