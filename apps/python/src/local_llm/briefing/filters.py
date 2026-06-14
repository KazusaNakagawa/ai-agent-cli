"""Filter / extraction helpers for URLs, dates, index pages, and Simplified Chinese.

A set of pure functions shared by the pre-fetch, rendering, and URL-validation stages.
"""

from __future__ import annotations

import re
from datetime import date

# Evergreen ticker index / quote pages that are not news articles. Their snippets
# contain no facts for the day and only pollute the prompt, so prune them before
# injection (#153).
_INDEX_PAGE_URL_PATTERNS = [
    re.compile(p)
    for p in (
        r"finance\.yahoo\.com/quote/",
        r"robinhood\.com/.*/stocks/",
        r"google\.com/finance",
        r"investing\.com/equities/",
        r"stockanalysis\.com/stocks/",
        r"seekingalpha\.com/symbol/",
        # CNBC quote/ticker pages (/quotes/SYMBOL). Keep articles (/YYYY/MM/DD/...).
        r"cnbc\.com/quotes/",
        # For Amazon, exclude only product-detail pages (/dp/, /gp/product/ —
        # product-name slug allowed). Do not target the whole domain so article
        # pages are not dropped.
        r"amazon\.(com|co\.jp)/(.+/)?(gp/product|dp)/",
        # Aggregator sites that pump out stock forecasts, analyst ratings, and 13F
        # spam (#158, #180). For marketbeat not only /stocks/ but also
        # /instant-alerts/ etc. are 13F spam factories, so exclude the whole domain.
        r"marketbeat\.com",
        r"simplywall\.st/stocks/",
        r"tipranks\.com/stocks/",
        r"wallstreetzen\.com/stocks/",
        r"cnn\.com/markets/stocks/",
        # Auto-generated 13F holdings-change spam & rating/hype sites (they
        # polluted the table in live testing). Their article bodies almost never
        # have primary info for the day, so exclude per-domain. fool.com /
        # 247wallst are not targeted because they also carry good articles.
        r"americanbankingnews\.com",
        r"dailypolitical\.com",
        r"themarketsdaily\.com",
        r"weissratings\.com",
        r"timothysykes\.com",
        r"stockstotrade\.com",
        # Quote / live-price index pages & valuation-forecast sites (#176).
        # indmoney is a per-ticker live-price page; trefis is forecast/valuation articles.
        r"indmoney\.com/us-stocks/",
        r"trefis\.com/stock/",
    )
]


def _is_index_page(url: str) -> bool:
    return any(p.search(url) for p in _INDEX_PAGE_URL_PATTERNS)


def _url_has_no_spaces(url: str) -> bool:
    """Check that the URL has no spaces (whitespace check only). Prevents Markdown link breakage (#181)."""
    return " " not in url


# Patterns for extracting the article date from a URL.
# Brave's freshness is a hint and can return old articles, so supplement it on the Python side.
_URL_DATE_YMD = re.compile(r"/(\d{4})[/-](\d{2})[/-](\d{2})(?:/|[-_])")  # /YYYY/MM/DD/ or /YYYY-MM-DD/
_URL_DATE_MDY = re.compile(r"-(\d{2})(\d{2})(\d{4})-")  # -MMDDYYYY- (Investopedia)


def _extract_url_date(url: str) -> date | None:
    """Return the date contained in the URL. None if no pattern matches or the date is invalid."""
    m = _URL_DATE_YMD.search(url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = _URL_DATE_MDY.search(url)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


# Set of Simplified-Chinese-specific characters, containing only code points that
# never appear in Japanese text. Lists characters where Traditional/Japanese use a
# different code point (为→為, 标→標, 对→対, 创→創, 历→歴, 发→発, 说→説, 变→変,
# 实→実, 响→響) and characters with no Japanese counterpart (么/这/们/该) (#179).
_SC_CHARS = re.compile(r"[么这们该为标对创历发说变实响]")


def has_simplified_chinese_text(text: str) -> bool:
    """True if it contains a Simplified-Chinese-specific code point (only SC-specific chars, not all Chinese) (#179)."""
    return bool(_SC_CHARS.search(text))


# Not excluding ) lets us correctly capture a ) inside the URL (#003 regression).
# The Markdown link closer's ) is stripped by _trim_md_link_closer.
_URL_RE = re.compile(r"https?://[^\s\]]+")


def _trim_md_link_closer(url: str) -> str:
    """Strip an unbalanced trailing ) from the URL (prevents the Markdown link `](url)` closer leaking in)."""
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url
