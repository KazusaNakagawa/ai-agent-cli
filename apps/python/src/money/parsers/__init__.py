"""Parser registry: pick a format from the file's own header, not its name.

Every parser turns one statement format into ``Transaction`` records with the
sign convention normalized (income positive). Format-specific quirks — text
encoding, column layout, one signed column vs separate withdrawal/deposit
columns — stop here and never reach the rest of the package.
"""
from __future__ import annotations

from pathlib import Path

from ..models import MoneyError, UnknownFormatError
from ..normalize import has_mojibake
from . import manual, rakuten_bank
from .base import ParseResult, build_transaction, parse_amount, verify_balance_chain

__all__ = [
    "ParseResult",
    "build_transaction",
    "detect",
    "parse_amount",
    "parse_file",
    "read_text",
    "verify_balance_chain",
]

# The sniffers are mutually exclusive, so order only decides which one is asked
# first.
PARSERS = (rakuten_bank, manual)

# UTF-8 is tried first on purpose. CP932 will happily "decode" a UTF-8 file into
# kanji garbage, whereas a CP932 statement of any length is essentially never
# valid UTF-8 — so this order fails loudly rather than silently.
ENCODINGS = ("utf-8-sig", "cp932")


def read_text(path: Path) -> str:
    """Decode a statement, refusing one whose characters were already lost."""
    raw = path.read_bytes()
    text = None
    for encoding in ENCODINGS:
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise MoneyError(f"{path.name}: could not decode as {' or '.join(ENCODINGS)}")
    if has_mojibake(text):
        raise MoneyError(
            f"{path.name}: contains replacement characters, so the original text is gone. "
            "Re-download the file and move it into place without opening it in an editor "
            "or spreadsheet, which is where the encoding is usually lost."
        )
    return text


def detect(text: str):
    """Return the parser whose sniffer recognizes this file's header."""
    for parser in PARSERS:
        if parser.sniff(text):
            return parser
    return None


def parse_file(path: Path) -> ParseResult:
    text = read_text(path)
    parser = detect(text)
    if parser is None:
        raise UnknownFormatError(
            f"{path.name}: no parser recognizes this file's header "
            f"(known formats: {', '.join(p.NAME for p in PARSERS)})"
        )
    return parser.parse(path, text)
