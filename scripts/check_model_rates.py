#!/usr/bin/env python3
"""Check the model rate table against what Claude Code transcripts actually show.

There is no pricing API to fetch rates from — the Models API returns ids,
context windows and capabilities, but no prices — so ``config/model_rates.json``
is hand-maintained and will drift. This script is what makes that drift loud
instead of silent, in two ways:

* **Unpriced models.** Any model id appearing in transcript ``message.usage``
  entries with no entry in the rate table. This is the failure that let
  claude-opus-5 report $0 for three weeks with only an amber line in the UI.
* **Rate drift.** Claude Code writes ``{"type": "cost-state"}`` records
  carrying a per-model ``modelUsage`` breakdown and the ``costUSD`` it charged.
  Recomputing that cost from our table and comparing catches a published price
  change, a new cache tier, or a typo in the config.

The reconciliation brackets rather than equates. ``modelUsage`` reports one
combined ``cacheCreationInputTokens`` with no 5-minute/1-hour split, and the
two TTLs are priced differently, so the true cost can land anywhere between an
all-5m and an all-1h reading. A record outside that bracket is drift; one
inside it is consistent with some split and cannot be faulted.

That bracket is also the check's blind spot, and worth knowing before trusting
a pass: on a write-heavy record the spread is wide, so a rate error smaller
than it goes unseen. Records with few or no cache writes are where the check
has teeth — there the bracket collapses to a point and a cent of error shows.

Exit codes: 0 when everything reconciles, 1 when anything does not.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "python"))

from src.claude_rates import RATES_PATH, load_rates  # noqa: E402

DEFAULT_TRANSCRIPTS = Path.home() / ".claude" / "projects"

# Real model ids that legitimately have no token price. "<synthetic>" is a
# CLI-internal message rather than a model call and always carries 0 tokens.
KNOWN_UNPRICED = frozenset({"<synthetic>"})

# A record has to miss the bracket by more than this to count as drift.
# Claude Code's own figures are floats accumulated over a session, so exact
# equality is not a fair bar — but the error there is rounding-scale, which is
# why the absolute floor stays tiny and the relative band does the work. A
# floor loose enough to hide a cent would blind the check on the small records
# that are its most sensitive evidence.
ABS_TOLERANCE_USD = 1e-6
REL_TOLERANCE = 0.005


def _iter_records(root: Path):
    """Yield parsed JSON objects from every transcript under root."""
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.jsonl")):
        try:
            f = open(path)
        except OSError:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def _token_cost_bracket(usage: dict, rate: tuple[float, ...]) -> tuple[float, float]:
    """Cost if every cache write were 5-minute, and if every one were 1-hour."""
    in_rate, out_rate, cw5m_rate, cw1h_rate, cr_rate = rate
    base = (
        usage.get("inputTokens", 0) * in_rate
        + usage.get("outputTokens", 0) * out_rate
        + usage.get("cacheReadInputTokens", 0) * cr_rate
    )
    cw = usage.get("cacheCreationInputTokens", 0)
    return ((base + cw * cw5m_rate) / 1e6, (base + cw * cw1h_rate) / 1e6)


def _describe(model: str, offenders: list[tuple[float, float, float]], total: int) -> str:
    """One line per drifting model: how widespread, plus the worst example."""
    actual, low, high = max(offenders, key=lambda o: max(o[1] - o[0], o[0] - o[2]))
    span = f"${low:.4f}" if abs(high - low) < 1e-9 else f"${low:.4f}–${high:.4f}"
    return (
        f"{model}: {len(offenders)} of {total} record(s) outside the expected cost; "
        f"worst — Claude Code recorded ${actual:.4f}, our table gives {span}"
    )


def check(
    root: Path, rates: dict[str, tuple[float, ...]]
) -> tuple[list[str], list[str], int]:
    """Return (unpriced model ids, drift descriptions, reconciled record count)."""
    unpriced: set[str] = set()
    offenders: dict[str, list[tuple[float, float, float]]] = {}
    per_model_total: dict[str, int] = {}
    reconciled = 0
    skipped_web_search = 0

    for record in _iter_records(root):
        message = record.get("message")
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            model = message.get("model", "unknown")
            if model not in rates and model not in KNOWN_UNPRICED:
                unpriced.add(model)

        if record.get("type") != "cost-state":
            continue

        for model, usage in (record.get("modelUsage") or {}).items():
            actual = usage.get("costUSD") or 0
            if not actual:
                continue
            if model not in rates:
                if model not in KNOWN_UNPRICED:
                    unpriced.add(model)
                continue
            if usage.get("webSearchRequests"):
                # Billed per request ($0.01 each) on top of tokens, which the
                # rate table does not model. Reconciling would always fail.
                skipped_web_search += 1
                continue

            low, high = _token_cost_bracket(usage, rates[model])
            tolerance = max(ABS_TOLERANCE_USD, actual * REL_TOLERANCE)
            reconciled += 1
            per_model_total[model] = per_model_total.get(model, 0) + 1
            if actual < low - tolerance or actual > high + tolerance:
                offenders.setdefault(model, []).append((actual, low, high))

    if skipped_web_search:
        print(f"  skipped {skipped_web_search} record(s) using web search (billed per request)")
    drift = [
        _describe(model, rows, per_model_total[model])
        for model, rows in sorted(offenders.items())
    ]
    return sorted(unpriced), drift, reconciled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--transcripts",
        type=Path,
        default=DEFAULT_TRANSCRIPTS,
        help=f"Claude Code transcript root (default: {DEFAULT_TRANSCRIPTS})",
    )
    parser.add_argument(
        "--rates",
        type=Path,
        default=RATES_PATH,
        help=f"rate table to check (default: {RATES_PATH})",
    )
    args = parser.parse_args(argv)

    rates = load_rates(args.rates)

    if not args.transcripts.is_dir():
        print(f"no transcripts found at {args.transcripts} — nothing to check")
        return 0

    unpriced, drift, reconciled = check(args.transcripts, rates)

    if unpriced:
        print("Models seen in transcripts with no entry in the rate table:")
        for model in unpriced:
            print(f"  {model}")
        print(f"\nAdd them to {args.rates} with their published rates.")
    if drift:
        print("Rates disagree with Claude Code's own cost records:")
        for line in drift:
            print(f"  {line}")

    if unpriced or drift:
        return 1

    print(f"OK — every model is priced; {reconciled} cost record(s) reconciled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
