"""Pure comparisons between a NormalizedOrder and text read back from the UI.

Section 5 (verification). Bridges the type gap between normalization's
typed values (Decimal money/percent, datetime.date) and what
ui_automation/vision_grounding actually return: plain strings, read from
an Edit's window_text() or a vision-grounded grid cell. Pure functions, no
UI/network - unit-tested the same way as entity_resolution/matching.py.

Money and percent parsing here mirror normalization.normalizer's locale-
tolerant parsing (dot- or comma-decimal, optional thousands separator,
optional currency symbol) but are written independently rather than
importing normalizer's module-private parser - the same choice
entity_resolution.matching.parse_vat_text already made for the same
reason: each section's own read-back parsing is its own small copy,
matching the precedent matching.py set, rather than reaching into another
module's private helper.
"""

from __future__ import annotations

import datetime
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fakturama_automation.entity_resolution.matching import parse_vat_text
from fakturama_automation.normalization.config import MONEY_QUANTIZE
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder

_CURRENCY_SYMBOLS = re.compile(r"[€$£]|\bEUR\b|\bUSD\b|\bGBP\b", re.IGNORECASE)

# Mirrors normalization.normalizer's date parsing: ISO first, with an
# unambiguous day-first fallback. Anything else does not parse (fails
# closed), consistent with CLAUDE.md's parsing conventions.
_DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y"]


def parse_money_text(text: str) -> Decimal | None:
    """Parse a monetary value read back from Fakturama's UI to a Decimal,
    or None if it doesn't parse (an unparseable read is never treated as
    a match - fail closed).
    """
    cleaned = _CURRENCY_SYMBOLS.sub("", text).strip().replace(" ", "").replace("\xa0", "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def money_equals(expected: Decimal, ui_text: str, *, tolerance: Decimal = Decimal("0.01")) -> bool:
    """Compare a normalized Decimal money value against UI text, within
    tolerance (default 1 cent, matching normalization's own line-total
    tolerance) to absorb rounding-mode differences between this pipeline
    and Fakturama's own arithmetic.
    """
    parsed = parse_money_text(ui_text)
    if parsed is None:
        return False
    return abs(parsed - expected) <= tolerance


def percent_equals(expected: Decimal, ui_text: str) -> bool:
    """Compare a normalized percentage (VAT or discount - both plain
    numbers per CLAUDE.md's parsing conventions) against UI text.

    Reuses entity_resolution.matching.parse_vat_text: VAT-percent parsing
    and discount-percent parsing are the same locale-tolerant "strip a
    trailing %, then parse" operation, so both use this one function
    rather than a second near-duplicate.
    """
    parsed = parse_vat_text(ui_text)
    if parsed is None:
        return False
    return parsed == expected


def text_equals(expected: str, ui_text: str) -> bool:
    """Trimmed, case-sensitive exact comparison - consistent with
    entity_resolution's exact-match-only stance (Doc/Design.md Tradeoffs):
    a near-miss is a mismatch, never "close enough".
    """
    return expected.strip() == ui_text.strip()


def parse_ui_date(text: str) -> datetime.date | None:
    """Parse a date read back from Fakturama's UI, or None if it doesn't
    parse. Mirrors normalization.normalizer's ISO-first/DD.MM.YYYY-fallback
    convention; an ambiguous or unrecognized format fails closed (None),
    never guessed.
    """
    stripped = text.strip()
    if not stripped:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


def date_equals(expected: datetime.date | None, ui_text: str) -> bool:
    """Compare a normalized date (or None, meaning "no date expected")
    against UI text.
    """
    if expected is None:
        return not ui_text.strip()
    return parse_ui_date(ui_text) == expected


def order_level_totals(order: NormalizedOrder) -> tuple[Decimal, Decimal, Decimal]:
    """Return (net_total, vat_total, gross_total) derived from
    order.line_items: the sum of each line's already-recomputed net total,
    the sum of each line's VAT amount (rounded per-line, half-up, matching
    normalization's own money rounding), and their sum.

    Shared by order_verification and invoice_verification so both compare
    against the same derived totals rather than each computing their own
    (CLAUDE.md's "keep this in exactly one place" rule, applied to this
    derived-totals formula the same way validators.recompute_line_total
    applies it to the line-total formula).
    """
    net_total = Decimal("0")
    vat_total = Decimal("0")
    for item in order.line_items:
        net_total += item.recomputed_total
        vat_total += (item.recomputed_total * item.vat_percent / Decimal(100)).quantize(
            MONEY_QUANTIZE, rounding=ROUND_HALF_UP
        )
    return net_total, vat_total, net_total + vat_total


def line_row_problems(expected: NormalizedLineItem, row: dict[str, str]) -> list[str]:
    """Compare one order/invoice line item against one row read back from
    the (vision-grounded) item grid. Returns a human-readable mismatch per
    discrepant field, or [] if the row matches on every field Task
    Description 3.13-3.16 checks (SKU, Qty., U.Price, VAT, Discount, and
    the recomputed line Price).
    """
    problems: list[str] = []
    label = expected.sku or "?"

    sku = row.get("SKU", "")
    if not text_equals(expected.sku, sku):
        problems.append(f"{label}: SKU expected '{expected.sku}', UI shows '{sku}'")

    qty_text = row.get("Qty.", "")
    if not money_equals(expected.quantity, qty_text):
        problems.append(f"{label}: Qty. expected {expected.quantity}, UI shows '{qty_text}'")

    price_text = row.get("U.Price", "")
    if not money_equals(expected.unit_net_price, price_text):
        problems.append(f"{label}: U.Price expected {expected.unit_net_price}, UI shows '{price_text}'")

    vat_text = row.get("VAT", "")
    if not percent_equals(expected.vat_percent, vat_text):
        problems.append(f"{label}: VAT expected {expected.vat_percent}, UI shows '{vat_text}'")

    discount_text = row.get("Discount", "")
    if not percent_equals(expected.discount, discount_text):
        problems.append(f"{label}: Discount expected {expected.discount}, UI shows '{discount_text}'")

    line_total_text = row.get("Price", "")
    if not money_equals(expected.recomputed_total, line_total_text):
        problems.append(f"{label}: Price expected {expected.recomputed_total}, UI shows '{line_total_text}'")

    return problems
