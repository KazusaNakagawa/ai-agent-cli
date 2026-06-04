"""Classifier for transient claude CLI failures that warrant a retry.

The claude CLI surfaces upstream Anthropic API errors and node-fetch
network errors verbatim in its stdout/stderr. Both categories include
genuinely transient conditions (overload, dropped sockets, DNS hiccups)
that recover within seconds, so ``run_claude`` retries them with
exponential backoff. Permanent errors (auth, bad request, invalid model)
must NOT be retried — retrying them only wastes the cron's wall-clock
budget and can amplify the failure.

This module is the single place to extend that policy: append a new
compiled pattern to ``_TRANSIENT_PATTERNS`` with a one-line comment
recording where the symptom was first observed.
"""

import re

_TRANSIENT_PATTERNS: list[re.Pattern[str]] = [
    # Anthropic API 5xx (e.g. "API Error: 529 Overloaded.")
    re.compile(r"API Error:\s*5\d\d"),
    # node-fetch socket-close (observed 2026-06-05 on briefing + weekly jobs)
    re.compile(r"socket connection was closed unexpectedly", re.IGNORECASE),
    # node-fetch generic network failure
    re.compile(r"\bfetch failed\b", re.IGNORECASE),
    # libc/Node networking errno strings bubbled up from the underlying fetch
    re.compile(r"\b(?:ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|ENETUNREACH)\b"),
]


def is_transient(stdout: str | None, stderr: str | None) -> bool:
    """Return True if the combined stdout+stderr matches a known transient
    failure signature.

    Callers should pair this with a bounded retry + exponential backoff
    policy. Never call in a tight loop — the patterns also match recoverable
    server overloads that need time to drain.
    """
    haystack = (stdout or "") + "\n" + (stderr or "")
    if not haystack.strip():
        return False
    return any(p.search(haystack) for p in _TRANSIENT_PATTERNS)
