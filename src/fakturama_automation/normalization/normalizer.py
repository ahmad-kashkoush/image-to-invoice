from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.extraction.models import RawAddress, RawLineItem, RawOrder
from fakturama_automation.normalization import config, parsing
from fakturama_automation.normalization.models import NormalizedAddress, NormalizedLineItem, NormalizedOrder
from fakturama_automation.normalization.validators import (
    check_confidence,
    check_line_total,
    check_required_fields,
)
_DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y"]


def normalize_order(
    raw_order: RawOrder,
    *,
    confidence_threshold: float = config.DEFAULT_CONFIDENCE_THRESHOLD,
    line_total_tolerance: Decimal = config.DEFAULT_LINE_TOTAL_TOLERANCE,
) -> NormalizedOrder:
    failures: list[str] = []

    order = NormalizedOrder(
        order_date=_parse_date(raw_order.order_date, "order_date", failures),
        external_reference=_trim(raw_order.external_reference),
        debtor_company_name=_trim(raw_order.debtor_company_name),
        contact_name=_trim(raw_order.contact_name),
        alias=_trim(raw_order.alias),
        billing_address=_normalize_address(raw_order.billing_address),
        delivery_address=_normalize_address(raw_order.delivery_address),
        payment_method=_trim(raw_order.payment_method),
        payment_status=_trim(raw_order.payment_status),
        payment_date=_parse_date(raw_order.payment_date, "payment_date", failures),
        line_items=[
            _normalize_line_item(item, index, failures) for index, item in enumerate(raw_order.line_items)
        ],
    )

    if not check_required_fields(order):
        failures.append(
            "missing required fields: a debtor company name and at least one line item "
            "with a SKU and positive quantity are required"
        )

    for index, item in enumerate(order.line_items):
        if not check_line_total(item, line_total_tolerance):
            failures.append(
                f"line {index + 1} ({item.sku or '?'}): recomputed total {item.recomputed_total} "
                f"does not match source total {item.source_line_total}"
            )

    if not check_confidence(raw_order, confidence_threshold):
        failures.append(f"one or more extracted fields fall below the confidence threshold ({confidence_threshold})")

    if failures:
        raise ManualReviewRequired(step="normalization", reason="; ".join(failures))

    return order


def _normalize_address(address: RawAddress) -> NormalizedAddress:
    return NormalizedAddress(
        street=_trim(address.street),
        postal_code=_trim(address.postal_code),
        city=_trim(address.city),
        country=_trim(address.country),
    )


def _normalize_line_item(item: RawLineItem, index: int, failures: list[str]) -> NormalizedLineItem:
    prefix = f"line_items[{index}]"
    # recomputed_total is not assigned here: NormalizedLineItem computes it
    # from its own fields, so it is correct for any line item however it was
    # built, not only for ones this function produced.
    return NormalizedLineItem(
        sku=_trim(item.sku),
        description=_trim(item.description),
        quantity=_parse_money(item.quantity, f"{prefix}.quantity", failures),
        unit_net_price=_parse_money(item.unit_net_price, f"{prefix}.unit_net_price", failures),
        vat_percent=_parse_percent(item.vat_percent, f"{prefix}.vat_percent", failures),
        discount=_parse_percent(item.discount, f"{prefix}.discount", failures),
        source_line_total=_parse_money(item.source_line_total, f"{prefix}.source_line_total", failures),
    )


def _trim(value: str | None) -> str:
    return value.strip() if value else ""


def _parse_date(value: str | None, field_name: str, failures: list[str]) -> datetime.date | None:
    text = _trim(value)
    if not text:
        return None
    parsed = parsing.parse_date_text(text, _DATE_FORMATS)
    if parsed is None:
        failures.append(f"{field_name}: unparseable date '{text}'")
    return parsed


def _parse_money(value: str | None, field_name: str, failures: list[str]) -> Decimal:
    text = _trim(value)
    if not text:
        return Decimal(0)
    parsed = parsing.parse_money_text(text)
    if parsed is None:
        failures.append(f"{field_name}: unparseable number '{text}'")
        return Decimal(0)
    return parsed.quantize(config.MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def _parse_percent(value: str | None, field_name: str, failures: list[str]) -> Decimal:
    text = _trim(value)
    if not text:
        return Decimal(0)
    # Not parsing.parse_percent_text: that searches for a "<number>%"
    # pattern anywhere, which is right for a dropdown label but wrong for a
    # document field - "abc 19%" is a misread here, not a percentage.
    parsed = parsing.parse_decimal(
        parsing.normalize_decimal_separators(parsing.strip_spaces(text.replace("%", "")))
    )
    if parsed is None:
        failures.append(f"{field_name}: unparseable percentage '{text}'")
        return Decimal(0)
    return parsed
