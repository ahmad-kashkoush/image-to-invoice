"""Validation checks run during fakturama_automation.normalization.

These checks decide whether a normalized order is safe to hand to the
orchestrator. Anything that fails stops the flow before automation starts
(normalizer.py raises ManualReviewRequired), rather than warning and
continuing.
"""

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
    """A line's net total per Task rule 3.16: quantity x unit net price x
    (1 - discount / 100). discount is a percentage; VAT is not part of the
    net line total. Rounded to 2 decimal places, half-up.

    The formula itself lives on NormalizedLineItem.recomputed_total, which
    computes it from the line's own fields rather than waiting to be
    assigned - so a line item cannot exist with an uncomputed total. This
    function stays as the named, importable expression of Task rule 3.16
    (and as check_line_total's own vocabulary) and delegates to it; there
    is still exactly one place the arithmetic is written.
    """
    return item.recomputed_total


def gross_from_net(net_price: Decimal, vat_percent: Decimal) -> Decimal:
    """Convert a net price to its VAT-inclusive gross equivalent:
    net x (1 + vat_percent / 100), rounded to 2 places, half-up.

    Every price this pipeline holds is net (CLAUDE.md's money convention),
    but Fakturama's Product editor takes a GROSS price - its field is
    labelled "Price (gross)" and it derives the net figure back out by
    dividing by (1 + VAT). Typing a net price straight into it therefore
    understates the product by exactly that factor everywhere it is later
    used. The single place that conversion is expressed, so nothing
    reimplements it - same rule as recompute_line_total above.
    """
    gross = net_price * (Decimal(1) + vat_percent / _HUNDRED)
    return gross.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def check_line_total(item: NormalizedLineItem, tolerance: Decimal) -> bool:
    """Recompute a line's total from quantity, unit price, and discount and
    compare it to the source line total within tolerance.

    A mismatch beyond tolerance means the extracted total does not agree
    with the extracted quantity/price/discount, signaling a misread field
    that must not reach automation silently.
    """
    return abs(recompute_line_total(item) - item.source_line_total) <= tolerance


def check_required_fields(order: NormalizedOrder) -> bool:
    """Confirm required fields are present: debtor name and at least one
    line item, each with a non-empty SKU (needed for exact-match product
    resolution) and a positive quantity.
    """
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
    """Return the name of the first field that was actually extracted (a
    non-None/non-empty raw value) but whose confidence is below threshold,
    or None if every extracted field clears it.

    A field the model never extracted (raw value is None/empty) is a
    completeness concern for check_required_fields, not a confidence
    failure here. A missing confidence key for an extracted field is
    treated as 0.0 (fail closed), per extraction/models.py's confidence
    keying convention.
    """
    for name in field_names:
        value = raw_values.get(name)
        if value is None or value == "":
            continue
        if confidence.get(name, 0.0) < threshold:
            return name
    return None


def check_confidence(raw_order: RawOrder, threshold: float) -> bool:
    """Confirm no field relevant to automation is below the confidence
    threshold after the OCR fallback pass.

    Confidence lives on the raw models (RawOrder/RawAddress/RawLineItem),
    not on NormalizedOrder, so this reads raw_order directly rather than
    the normalized result (see extraction/models.py's confidence keying
    convention docstring).
    """
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
