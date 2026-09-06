"""Shared per-model pricing table for Claude token cost estimation.

Used by src.usage_monitor, scripts/token_usage_report.py, and
scripts/sdd_token_cost.py so the rates are maintained in one place.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# USD per 1M tokens: (input, output, cache_write, cache_read)
# Source: published Anthropic API pricing as of 2026-09.
# Cache rates follow the standard multipliers on the input rate (write 1.25x,
# read 0.1x) unless a model publishes its own, as Claude Fable 5.1 does.
# Keyed by exact model id; add new ids here as models are released rather
# than relying on substring matching, which can mis-map as model names
# evolve (e.g. a future id containing "claude-sonnet-5" as a substring but
# priced differently).
RATES = {
    "claude-fable-5-1": (10.00, 50.00, 12.50, 0.25),
    "claude-fable-5": (10.00, 50.00, 12.50, 1.00),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-7": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-6": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 0.20),
    "claude-sonnet-4-6": (3.00, 15.00, 3.75, 0.30),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10),
    "claude-haiku-4-5-20251001": (1.00, 5.00, 1.25, 0.10),
}

# Process-global so a long batch run logs each unknown model once instead of
# once per message. That makes it shared state between tests — see
# reset_unpriced_warnings().
_unpriced_models_warned: set[str] = set()


def reset_unpriced_warnings() -> None:
    """Forget which models have already been warned about.

    Test-support hook: without it the first suite to hit an unknown model
    suppresses the warning for every later test in the same process, so
    assertions on the warning pass or fail depending on collection order.
    """
    _unpriced_models_warned.clear()


def rate_for(model: str) -> tuple[float, float, float, float]:
    """Return the rate tuple for a model, warning once per unknown model."""
    if model in RATES:
        return RATES[model]
    if model not in _unpriced_models_warned:
        _unpriced_models_warned.add(model)
        logger.warning("no rate table entry for model '%s' — cost shown as $0", model)
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
