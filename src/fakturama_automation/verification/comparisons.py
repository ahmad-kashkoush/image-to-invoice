
from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from fakturama_automation.normalization import parsing
from fakturama_automation.normalization.config import MONEY_QUANTIZE
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.ui_automation import screens
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d. %b %Y",
    "%d. %B %Y",
]


def parse_money_text(text: str) -> Decimal | None:
    return parsing.parse_money_text(text)


def money_equals(expected: Decimal, ui_text: str, *, tolerance: Decimal = Decimal("0.01")) -> bool:
    parsed = parse_money_text(ui_text)
    if parsed is None:
        return False
    return abs(parsed - expected) <= tolerance


def percent_equals(expected: Decimal, ui_text: str) -> bool:
    parsed = parsing.parse_percent_text(ui_text)
    if parsed is None:
        return False
    return parsed == expected


def text_equals(expected: str, ui_text: str) -> bool:
    return expected.strip() == ui_text.strip()


def parse_ui_date(text: str) -> datetime.date | None:
    return parsing.parse_date_text(text, _DATE_FORMATS)


def date_equals(expected: datetime.date | None, ui_text: str) -> bool:
    if expected is None:
        return not ui_text.strip()
    return parse_ui_date(ui_text) == expected


def order_level_totals(order: NormalizedOrder) -> tuple[Decimal, Decimal, Decimal]:
    net_total = Decimal("0")
    vat_total = Decimal("0")
    for item in order.line_items:
        net_total += item.recomputed_total
        vat_total += (item.recomputed_total * item.vat_percent / Decimal(100)).quantize(
            MONEY_QUANTIZE, rounding=ROUND_HALF_UP
        )
    return net_total, vat_total, net_total + vat_total


def line_row_problems(expected: NormalizedLineItem, row: dict[str, str]) -> list[str]:
    problems: list[str] = []
    label = expected.sku or "?"
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
