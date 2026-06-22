"""Extract metrics for Notion number properties from the briefing text."""
import re


def extract_briefing_metrics(text: str, tickers: list[str]) -> dict:
    """Return character count and mentioned-ticker count in Notion extra_properties form.

    Tickers are matched with ASCII alphanumeric/underscore lookarounds. ``\\b``
    cannot detect cases directly adjacent to a Japanese particle (e.g. "PLTRは上昇"),
    so (?<![A-Za-z0-9_])TICKER(?![A-Za-z0-9_]) is used instead.

    Returns:
        {"CharCount": {"number": N}, "TickerCount": {"number": M}}
    """
    char_count = len(text)
    ticker_count = sum(
        1 for t in tickers
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])",
            text,
            re.IGNORECASE,
        )
    )
    return {
        "CharCount": {"number": char_count},
        "TickerCount": {"number": ticker_count},
    }
