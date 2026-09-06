from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fakturama_automation.extraction.models import (
    ADDRESS_CONFIDENCE_FIELDS,
    LINE_ITEM_CONFIDENCE_FIELDS,
    ORDER_LEVEL_CONFIDENCE_FIELDS,
    RawOrder,
)
from fakturama_automation.normalization.config import MONEY_QUANTIZE
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder

_HUNDRED = Decimal(100)


def recompute_line_total(item: NormalizedLineItem) -> Decimal:
    # Task rule 3.16: quantity x unit net price x (1 - discount / 100).
    # The arithmetic lives on NormalizedLineItem.recomputed_total, so a line
    return item.recomputed_total


def gross_from_net(net_price: Decimal, vat_percent: Decimal) -> Decimal:
    # Every price this pipeline holds is net, but Fakturama's Product editor
    # takes a GROSS price and derives net back out by dividing by (1 + VAT).
    # Typing a net price straight into it understates the product by exactly
    # that factor everywhere it is later used.
    gross = net_price * (Decimal(1) + vat_percent / _HUNDRED)
    return gross.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def check_line_total(item: NormalizedLineItem, tolerance: Decimal) -> bool:
    return abs(recompute_line_total(item) - item.source_line_total) <= tolerance


def check_required_fields(order: NormalizedOrder) -> bool:
    if not order.debtor_company_name:
        return False
    if not order.line_items:
        return False
    return all(item.sku and item.quantity > 0 for item in order.line_items)


def _extracted_confidence_shortfall(
    raw_values: dict[str, object | None],
    confidence: dict[str, float],
    field_names: list[str],
    threshold: float,
) -> str | None:
    # A field the model never extracted is a completeness concern for
    # check_required_fields, not a confidence failure here. A missing
    # confidence key for a field that *was* extracted counts as 0.0.
    for name in field_names:
        value = raw_values.get(name)
        if value is None or value == "":
            continue
        if confidence.get(name, 0.0) < threshold:
            return name
    return None


def check_confidence(raw_order: RawOrder, threshold: float) -> bool:
    # Confidence lives on the raw models, not on NormalizedOrder, so this
    # reads raw_order rather than the normalized result.
    order_values = {name: getattr(raw_order, name) for name in ORDER_LEVEL_CONFIDENCE_FIELDS}
    if _extracted_confidence_shortfall(
        order_values, raw_order.confidence, ORDER_LEVEL_CONFIDENCE_FIELDS, threshold
    ):
        return False

    for address in (raw_order.billing_address, raw_order.delivery_address):
        address_values = {name: getattr(address, name) for name in ADDRESS_CONFIDENCE_FIELDS}
        if _extracted_confidence_shortfall(
            address_values, address.confidence, ADDRESS_CONFIDENCE_FIELDS, threshold
        ):
            return False

    for item in raw_order.line_items:
        item_values = {name: getattr(item, name) for name in LINE_ITEM_CONFIDENCE_FIELDS}
        if _extracted_confidence_shortfall(
            item_values, item.confidence, LINE_ITEM_CONFIDENCE_FIELDS, threshold
        ):
            return False

    return True
