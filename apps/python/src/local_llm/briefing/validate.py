"""Match URLs in the model output against the pre-fetch whitelist to surface fabrication."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .filters import _trim_md_link_closer, _URL_RE
from .prefetch import PrefetchedContext


@dataclass(frozen=True)
class UrlValidation:
    body: str  # body after replacing fabricated URLs with <URL未検証>
    total: int
    fabricated: int

    @property
    def verified(self) -> int:
        return self.total - self.fabricated


def validate_urls(body: str, ctx: PrefetchedContext) -> UrlValidation:
    """Post-validate: replace URLs in the model output that are not from pre-fetch with `<URL未検証>`.

    Even when URLs are provided via pre-fetch, qwen2.5:14b more than 50% of the
    time **fabricates plausible-looking URLs** such as Yahoo Finance / Robinhood
    ticker pages. To guarantee the body's trustworthiness, match against the
    whitelist on the Python side and surface the fabricated portion.
    """
    allowed = ctx.allowed_urls
    total = 0
    fabricated = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal total, fabricated
        total += 1
        raw = match.group(0)
        url = _trim_md_link_closer(raw)
        suffix = raw[len(url):]
        if url in allowed:
            return raw
        fabricated += 1
        return "<URL未検証>" + suffix

    cleaned = _URL_RE.sub(_replace, body)
    return UrlValidation(body=cleaned, total=total, fabricated=fabricated)
