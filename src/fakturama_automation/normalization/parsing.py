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
