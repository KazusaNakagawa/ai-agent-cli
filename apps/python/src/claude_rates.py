"""Shared per-model pricing table for Claude token cost estimation.

Used by src.usage_monitor, scripts/token_usage_report.py, and
scripts/sdd_token_cost.py so the rates are maintained in one place.

The rates themselves live in ``config/model_rates.json`` rather than in this
module. There is no pricing API to fetch them from — the Models API returns
ids, context windows and capabilities but no prices — so the table is
hand-maintained, and ``scripts/check_model_rates.py`` is what catches a model
that has appeared in transcripts without one. See
``docs/guides/usage-monitoring.md``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

RATES_PATH = Path(
    os.getenv(
        "MODEL_RATES_PATH", str(Path(__file__).parents[1] / "config" / "model_rates.json")
    )
)

# Order matters: the loaded tuple is (input, output, cache_write_5m,
# cache_write_1h, cache_read) and every consumer unpacks it positionally.
RATE_FIELDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")


def load_rates(path: Path) -> dict[str, tuple[float, float, float, float, float]]:
    """Read a rate table from ``path``, in USD per 1M tokens.

    Every field is required per model. A partially specified model is rejected
    rather than defaulted, because a silent 0 for one component is exactly the
    failure this file exists to prevent.
    """
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise FileNotFoundError(f"model rate table not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e

    if not isinstance(raw, dict) or not isinstance(raw.get("rates"), dict):
        raise ValueError(f"{path} must contain a top-level 'rates' object")

    table: dict[str, tuple[float, float, float, float, float]] = {}
    for model, fields in raw["rates"].items():
        if not isinstance(fields, dict):
            raise ValueError(f"{path}: rates for {model!r} must be an object")
        values = []
        for name in RATE_FIELDS:
            if name not in fields:
                raise ValueError(f"{path}: {model!r} is missing the {name!r} rate")
            value = fields[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{path}: {model!r} has a non-numeric {name!r} rate")
            if value < 0:
                raise ValueError(f"{path}: {model!r} has a negative {name!r} rate")
            values.append(float(value))
        table[model] = tuple(values)  # type: ignore[assignment]
    return table


RATES = load_rates(RATES_PATH)

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


def rate_for(model: str) -> tuple[float, float, float, float, float]:
    """Return the rate tuple for a model, warning once per unknown model."""
    if model in RATES:
        return RATES[model]
    if model not in _unpriced_models_warned:
        _unpriced_models_warned.add(model)
        logger.warning("no rate table entry for model '%s' — cost shown as $0", model)
    return (0.0, 0.0, 0.0, 0.0, 0.0)


def usage_cost(usage: dict, model: str) -> float:
    """Estimate USD cost for one usage dict under the given model's rates.

    A 1-hour cache write costs 2x input where a 5-minute write costs 1.25x, so
    the two are billed apart. Transcripts carry the split under
    ``usage["cache_creation"]``; the 5-minute share is taken as the remainder
    of ``cache_creation_input_tokens`` so an entry without that breakdown (or
    with an unrecognised TTL) falls back to the cheaper rate rather than being
    dropped.
    """
    in_rate, out_rate, cw5m_rate, cw1h_rate, cr_rate = rate_for(model)
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    breakdown = usage.get("cache_creation") or {}
    cw_1h = min(breakdown.get("ephemeral_1h_input_tokens", 0), cw)
    cw_5m = cw - cw_1h
    return (
        inp * in_rate
        + out * out_rate
        + cw_5m * cw5m_rate
        + cw_1h * cw1h_rate
        + cr * cr_rate
    ) / 1_000_000
