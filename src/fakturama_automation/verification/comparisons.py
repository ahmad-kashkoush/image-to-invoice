"""Pure comparisons between a NormalizedOrder and text read back from the UI.

Bridges the type gap between normalization's typed values (Decimal money/
percent, datetime.date) and what ui_automation returns: plain strings. Pure
functions, no UI/network.

Number parsing comes from normalization.parsing, shared with the normalizer
rather than re-derived here. Only the accepted *date formats* are this
module's own, because they are a policy choice: this parses what a widget
renders, not what a human wrote.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from fakturama_automation.normalization import parsing
from fakturama_automation.normalization.config import MONEY_QUANTIZE
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.ui_automation import screens

# ISO first, with an unambiguous day-first fallback, as the normalizer has.
#
# The month-name forms are here because this parses text the UI *renders*,
# not text a human wrote: the Invoice's payment-date widget is written as
# ISO (the orchestrator's apply_payment step) but redisplays the value in the
# platform's medium date format ("Jul 18, 2026"), so a correctly applied
# date read straight back was failing to parse. A spelled-out month can't
# be confused for a day, so these stay unambiguous - a numeric slash date
# (MM/DD vs DD/MM) still fails closed rather than being guessed.
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d. %b %Y",
    "%d. %B %Y",
]


def parse_money_text(text: str) -> Decimal | None:
    """Parse a monetary value read back from Fakturama's UI, or None if
    it doesn't parse (an unparseable read is never treated as a match).
    """
    return parsing.parse_money_text(text)


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

    VAT-percent and discount-percent parsing are the same operation, so
    both go through normalization.parsing rather than a near-duplicate.
    """
    parsed = parsing.parse_percent_text(ui_text)
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
    return parsing.parse_date_text(text, _DATE_FORMATS)


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

    # Keys come from ui_automation.screens, which is also what built the
    # column list the vision read was given - so a row this function looks
    # up can only be a row that grid actually has. These are the grid's own
    # visible headers ("Item No.", not "SKU"), and used to be repeated here
    # as literals for the reader to keep in sync by hand.
    sku = row.get(screens.ITEMS_COL_SKU, "")
    if not text_equals(expected.sku, sku):
        problems.append(f"{label}: SKU expected '{expected.sku}', UI shows '{sku}'")

    qty_text = row.get(screens.ITEMS_COL_QUANTITY, "")
    if not money_equals(expected.quantity, qty_text):
        problems.append(f"{label}: Qty. expected {expected.quantity}, UI shows '{qty_text}'")

    price_text = row.get(screens.ITEMS_COL_UNIT_PRICE, "")
    if not money_equals(expected.unit_net_price, price_text):
        problems.append(f"{label}: U.Price expected {expected.unit_net_price}, UI shows '{price_text}'")

    vat_text = row.get(screens.ITEMS_COL_VAT, "")
    if not percent_equals(expected.vat_percent, vat_text):
        problems.append(f"{label}: VAT expected {expected.vat_percent}, UI shows '{vat_text}'")

    discount_text = row.get(screens.ITEMS_COL_DISCOUNT, "")
    if not percent_equals(expected.discount, discount_text):
        problems.append(f"{label}: Discount expected {expected.discount}, UI shows '{discount_text}'")

    line_total_text = row.get(screens.ITEMS_COL_LINE_TOTAL, "")
    if not money_equals(expected.recomputed_total, line_total_text):
        problems.append(f"{label}: Price expected {expected.recomputed_total}, UI shows '{line_total_text}'")

    return problems
