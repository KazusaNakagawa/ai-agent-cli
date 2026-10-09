"""Check the model rate table against what Claude Code transcripts actually show.

There is no pricing API to fetch rates from — the Models API returns ids,
context windows and capabilities, but no prices — so ``src/model_rates.json``
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

``--check-upstream`` also diffs the table against the published pricing doc.
That only prints: the doc is a web page rather than an API contract, so every
change to the table stays a human decision, and the diff never affects the
exit code.

Exit codes: 0 when everything reconciles, 1 when anything does not.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from src.claude_rates import RATE_FIELDS, RATES_PATH, load_rates

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


def _iter_records(root: Path, skipped: dict[str, int]):
    """Yield parsed JSON objects from every transcript under root.

    Unreadable files and unparseable lines are counted in ``skipped`` rather
    than raised: a transcript Claude Code is still writing can end in a partial
    line, and failing the daily run on that would be noise. The counts are
    printed so a scan that skipped something never reads as a clean one.
    """
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.jsonl")):
        try:
            f = open(path)
        except OSError:
            skipped["files"] += 1
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    skipped["lines"] += 1


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
    skipped = {"files": 0, "lines": 0}

    for record in _iter_records(root, skipped):
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

    if skipped["files"]:
        print(f"  skipped {skipped['files']} unreadable transcript file(s)")
    if skipped["lines"]:
        print(f"  skipped {skipped['lines']} unparseable line(s) (e.g. a session still being written)")
    if skipped_web_search:
        print(f"  skipped {skipped_web_search} record(s) using web search (billed per request)")
    drift = [
        _describe(model, rows, per_model_total[model])
        for model, rows in sorted(offenders.items())
    ]
    return sorted(unpriced), drift, reconciled


# --- upstream pricing doc (advisory) ---

PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"

_PRICE = re.compile(r"\$([0-9.]+)")
_DATED_ID = re.compile(r"-\d{8}$")


def display_name_to_id(name: str) -> str:
    """``"Claude Opus 5.5 (retired …)"`` -> ``"claude-opus-5-5"``."""
    base = name.split("(", 1)[0].strip().lower()
    return re.sub(r"[\s.]+", "-", base)


def parse_pricing_table(markdown: str) -> tuple[dict[str, tuple[float, ...]], set[str]]:
    """Read the main per-model table of the pricing doc into rate tuples.

    Returns ``(rates, tiered)``. A model listed on more than one row — priced
    by prompt length, like Claude Haiku 5.5 — cannot be expressed as one rate
    tuple, so it lands in ``tiered`` instead of ``rates``.
    """
    lines = markdown.splitlines()
    try:
        start = next(
            i for i, line in enumerate(lines)
            if line.startswith("|") and "5m cache writes" in line
        )
    except StopIteration:
        raise ValueError("no model pricing table found in the pricing doc") from None

    rows: dict[str, list[tuple[float, ...]]] = {}
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        name, base_in, cw5m, cw1h, read, out = [c.strip() for c in line.strip().strip("|").split("|")][:6]
        # Same order as RATE_FIELDS; the doc's columns put output last.
        prices = []
        for cell in (base_in, out, cw5m, cw1h, read):
            match = _PRICE.search(cell)
            if match is None:
                raise ValueError(f"no price in pricing table cell {cell!r} for {name!r}")
            prices.append(float(match.group(1)))
        rows.setdefault(display_name_to_id(name), []).append(tuple(prices))

    rates = {model: found[0] for model, found in rows.items() if len(found) == 1}
    tiered = {model for model, found in rows.items() if len(found) > 1}
    return rates, tiered


def diff_upstream(
    local: dict[str, tuple[float, ...]],
    upstream: dict[str, tuple[float, ...]],
    tiered: set[str],
) -> list[str]:
    """Human-readable differences between the table and the pricing doc.

    Dated ids (``claude-haiku-4-5-20251001``) are compared against their
    undated family row, since the doc lists only the family name.
    """
    lines = []
    for model, rate in sorted(local.items()):
        family = _DATED_ID.sub("", model)
        if family in tiered:
            # One rate tuple cannot express prompt-length pricing.
            lines.append(f"tiered, not modelled: {model} (table has a single rate)")
            continue
        if family not in upstream:
            lines.append(f"not in pricing doc: {model}")
            continue
        changes = [
            f"{field} {old:g} -> {new:g}"
            for field, old, new in zip(RATE_FIELDS, rate, upstream[family])
            if abs(old - new) > 1e-9
        ]
        if changes:
            lines.append(f"changed {model}: {', '.join(changes)}")
    known = {_DATED_ID.sub("", m) for m in local}
    lines += [f"not in table: {m}" for m in sorted(set(upstream) - known)]
    lines += [f"tiered, not modelled: {m}" for m in sorted(tiered - known)]
    return lines


def fetch_pricing_doc() -> str:
    # The docs host answers urllib's default User-Agent with 403.
    request = urllib.request.Request(PRICING_URL, headers={"User-Agent": "ai-agent-cli rate_check"})
    with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310 — fixed https URL
        return resp.read().decode("utf-8")


def _print_upstream_diff(rates: dict[str, tuple[float, ...]]) -> None:
    print(f"Pricing doc ({PRICING_URL}):")
    try:
        upstream, tiered = parse_pricing_table(fetch_pricing_doc())
    except (OSError, ValueError) as e:
        # Advisory only: an unreachable or reshaped doc must not mask the
        # transcript checks, which alone decide the exit code.
        print(f"  could not check: {e}")
        return
    for line in diff_upstream(rates, upstream, tiered) or ["no differences"]:
        print(f"  {line}")


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
    parser.add_argument(
        "--check-upstream",
        action="store_true",
        help="also diff the table against the published pricing doc (prints only, never writes)",
    )
    args = parser.parse_args(argv)

    # A broken table is the very thing this script reports on, so it gets the
    # same treatment as any other finding rather than a traceback.
    try:
        rates = load_rates(args.rates)
    except (OSError, ValueError) as e:
        print(f"Rate table cannot be read: {e}")
        return 1

    if args.check_upstream:
        _print_upstream_diff(rates)

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
