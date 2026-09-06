"""Locale-tolerant parsing of numbers and dates out of text.

One home for the separator rule that used to exist in three near-identical
copies (the normalizer's own `_normalize_numeric_text`, verification's
`parse_money_text`, entity resolution's `parse_vat_text`) - and, with it,
the removal of `verification` importing `entity_resolution` just to reach
the third.

What is deliberately *not* unified is what each caller composes from these
primitives. Raw document text, UI-rendered text and a dropdown label have
genuinely different input spaces, and collapsing them would loosen parsing
in ways CLAUDE.md's fail-closed rule rules out - so the primitives are
shared and the compositions stay separate and explicit at each call site.
The date formats are the clearest case: the normalizer accepts only ISO and
an unambiguous day-first fallback, while verification also accepts the
month-name forms Fakturama's own widgets render.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = re.compile(r"[€$£]|\bEUR\b|\bUSD\b|\bGBP\b", re.IGNORECASE)

# A number followed by "%" anywhere in the text, so a prefixed label parses
# too - the Order editor's VAT dropdown names each option "{Name} ({Value}%)"
# rather than showing a bare value.
_NUMBER_WITH_PERCENT = re.compile(r"([\d.,]+)\s*%")


def strip_currency_symbols(text: str) -> str:
    """Remove currency symbols and ISO codes."""
    return CURRENCY_SYMBOLS.sub("", text)


def strip_spaces(text: str) -> str:
    """Remove every space, including the non-breaking spaces Fakturama uses
    as a thousands separator in some locales.
    """
    return text.replace(" ", "").replace("\xa0", "")


def normalize_decimal_separators(text: str) -> str:
    """Rewrite a number's decimal and thousands separators to plain dot
    notation, covering dot-decimal (the source documents this system
    targets) and European comma-decimal alike.

    Whitespace is *not* touched here: callers that should tolerate spaces
    inside a number strip them first, and the one that should not (percent
    text read off a dropdown) does not. Folding the strip in would make
    "1 9" parse as 19.
    """
    cleaned = text
    if "," in cleaned and "." in cleaned:
        # Whichever separator appears last is the decimal point; the other
        # is a thousands separator, e.g. "1.234,56" (EU) or "1,234.56" (US).
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Only a comma: treat it as the decimal separator (European style).
        cleaned = cleaned.replace(",", ".")
    return cleaned


def parse_decimal(text: str) -> Decimal | None:
    """Decimal(text), or None if it does not parse. No cleaning - callers
    compose the cleaning they need first.
    """
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_money_text(text: str) -> Decimal | None:
    """Parse a monetary value written by a human or rendered by the UI:
    currency symbols and spaces removed, either separator convention
    accepted. None if it does not parse - an unparseable amount is never
    treated as a match.
    """
    return parse_decimal(normalize_decimal_separators(strip_spaces(strip_currency_symbols(text))))


def parse_percent_text(text: str) -> Decimal | None:
    """Parse a percentage out of UI text, as a plain number: "19", "19.00",
    "19 %", "19,00 %" and "VAT 19 (19%)" all give Decimal("19").

    Finds a "<number>%" pattern anywhere first, falling back to the whole
    trimmed text for a bare value with no sign. Returns None rather than
    raising: an unparseable row is not evidence of a match, and the
    zero/one/many counting downstream still fails closed on what remains.
    """
    match = _NUMBER_WITH_PERCENT.search(text)
    cleaned = match.group(1) if match is not None else text.strip()
    return parse_decimal(normalize_decimal_separators(cleaned))


def parse_date_text(text: str, formats: list[str]) -> datetime.date | None:
    """Parse a date against `formats` in order, or None.

    The caller supplies the formats because the acceptable set is a policy
    decision, not a parsing one: text a human wrote and text a widget
    rendered are different input spaces. An unrecognised or ambiguous format
    fails closed here rather than being guessed.
    """
    stripped = text.strip()
    if not stripped:
        return None
    for fmt in formats:
        try:
            return datetime.datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None
