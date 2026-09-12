from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = re.compile(r"[€$£]|\bEUR\b|\bUSD\b|\bGBP\b", re.IGNORECASE)

# ISO 4217 codes this system recognizes as unambiguous when spelled out in
# full (the code itself names exactly one currency, unlike a bare symbol).
_KNOWN_ISO_CODES = {
    "EUR", "GBP", "USD", "CHF", "JPY", "CNY", "CAD", "AUD", "NZD",
    "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
}

# A symbol that names exactly one currency in this deployment's target
# market (see ADR 0012) - unambiguous, maps straight to its ISO code.
_UNAMBIGUOUS_SYMBOLS = {"€": "EUR", "£": "GBP"}

# A bare word alongside the symbol/code forms above - still unambiguous.
_CURRENCY_WORDS = {
    "EURO": "EUR", "EUROS": "EUR",
    "POUND": "GBP", "POUNDS": "GBP", "STERLING": "GBP", "POUND STERLING": "GBP",
}

# Symbols shared by more than one currency (e.g. "$" is USD/CAD/AUD/.../"¥"
# is JPY/CNY) - never guessed, per this repo's "ambiguous -> fail closed"
# rule (see ADR 0012).
_AMBIGUOUS_SYMBOLS = {"$", "¥"}

# A number followed by "%" anywhere in the text, so a prefixed label parses
# too - the Order editor's VAT dropdown names each option "{Name} ({Value}%)"
# rather than showing a bare value.
_NUMBER_WITH_PERCENT = re.compile(r"([\d.,]+)\s*%")


def strip_currency_symbols(text: str) -> str:
    return CURRENCY_SYMBOLS.sub("", text)


def strip_spaces(text: str) -> str:
    return text.replace(" ", "").replace("\xa0", "")


def normalize_decimal_separators(text: str) -> str:
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
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_money_text(text: str) -> Decimal | None:
    return parse_decimal(normalize_decimal_separators(strip_spaces(strip_currency_symbols(text))))


def parse_percent_text(text: str) -> Decimal | None:
    match = _NUMBER_WITH_PERCENT.search(text)
    cleaned = match.group(1) if match is not None else text.strip()
    return parse_decimal(normalize_decimal_separators(cleaned))


def canonicalize_currency(text: str) -> str | None:
    # Returns an ISO 4217 code for unambiguous input, else None - the caller
    # (normalizer._canonicalize_currency) treats None as a failure closed,
    # never guessing between e.g. USD/CAD/AUD for a bare "$".
    stripped = text.strip()
    if not stripped:
        return None
    if stripped in _UNAMBIGUOUS_SYMBOLS:
        return _UNAMBIGUOUS_SYMBOLS[stripped]
    if stripped in _AMBIGUOUS_SYMBOLS:
        return None
    upper = stripped.upper()
    if upper in _KNOWN_ISO_CODES:
        return upper
    if upper in _CURRENCY_WORDS:
        return _CURRENCY_WORDS[upper]
    return None


def parse_date_text(text: str, formats: list[str]) -> datetime.date | None:
    stripped = text.strip()
    if not stripped:
        return None
    for fmt in formats:
        try:
            return datetime.datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None
