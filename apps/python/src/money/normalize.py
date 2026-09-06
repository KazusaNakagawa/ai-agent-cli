"""Description normalization, match keys, and the dedup id.

Japanese bank statements spell the same counterparty many different ways, so
two derived strings are kept per transaction:

``desc``      normalized for display — readable, still distinguishes entries.
``desc_key``  folded further for matching — small kana, long marks, spacing and
              billing-period suffixes removed, so a human writing a rule can use
              the spelling the world uses rather than the bank's.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# U+309B/U+FF9E arrive as standalone characters rather than combining marks, so
# NFKC alone leaves "セ゛" instead of "ゼ". Swapping in the combining forms first
# lets NFKC compose them. NFKC's own decomposition of U+309B inserts a space,
# which is why this has to happen before normalization rather than after.
_VOICED_MARKS = {
    "゛": "゙",  # ゛ -> combining voiced
    "ﾞ": "゙",
    "゜": "゚",  # ゜ -> combining semi-voiced
    "ﾟ": "゚",
}

# Statements use a full-width hyphen where a katakana long mark belongs; NFKC
# turns it into "-", which makes カタカナ words unreadable.
_LONG_MARK_AFTER_KANA = re.compile(r"(?<=[ァ-ヶ])-")

# Billing-period suffixes ("6月分", "26年 7月"). Utility charges carry them, so
# without stripping these the same counterparty looks new every single month and
# never reaches the recurrence threshold.
_PERIOD_SUFFIXES = (
    re.compile(r"\d{1,2}\s*月分"),
    re.compile(r"\d{2,4}\s*年\s*\d{1,2}\s*月"),
)

# Statements write ッ ャ ュ as full-size; folding both directions lets a rule
# written the normal way match the bank's spelling.
_SMALL_KANA = str.maketrans("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")

REPLACEMENT_CHAR = "�"


def normalize_description(text: str) -> str:
    """Collapse a statement's spelling quirks into readable, stable text."""
    for mark, combining in _VOICED_MARKS.items():
        text = text.replace(mark, combining)
    text = unicodedata.normalize("NFKC", text)
    text = _LONG_MARK_AFTER_KANA.sub("ー", text)
    return " ".join(text.split())


def match_key(text: str) -> str:
    """Fold a description down to the key rules and grouping match on."""
    key = normalize_description(text)
    for pattern in _PERIOD_SUFFIXES:
        key = pattern.sub("", key)
    key = key.translate(_SMALL_KANA)
    return key.replace("ー", "").replace(" ", "").upper()


# An outgoing bank transfer records the sender's name — yours — alongside the
# recipient's. Searching the whole line for your own name therefore matches
# every payment you have ever made, not just moves between your own accounts.
_REQUESTER_ANNOTATION = "依頼人名"


def counterparty_key(desc_key: str) -> str:
    """The part of a match key that names the other party, not the sender.

    Everything from the requester annotation onward is dropped. A genuine
    transfer to your own account still matches, because your name appears as
    the recipient as well — before the annotation.
    """
    return desc_key.split(_REQUESTER_ANNOTATION, 1)[0]


def has_mojibake(text: str) -> bool:
    """True when the text carries U+FFFD, i.e. bytes were already lost.

    A CP932 file read as UTF-8 and saved again keeps its numbers intact but
    destroys the counterparty names, so every arithmetic check still passes
    while the file is useless for categorization. This is the only check that
    catches it.
    """
    return REPLACEMENT_CHAR in text


def transaction_id(account: str, date: str, amount: int, desc_key: str, balance: int | None) -> str:
    """Stable identity for a statement line, so re-importing a file is a no-op.

    The balance is part of the key because a genuine duplicate is possible:
    the same amount can be paid to the same counterparty twice on one day, and
    only the running balance tells those two lines apart.
    """
    parts = [account, date, str(amount), desc_key, "" if balance is None else str(balance)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
