"""Top level normalization entry point.

Section 2 (normalization). Converts every field on a RawOrder into its
typed, canonical NormalizedOrder counterpart (ISO dates, rounded Decimal
money, plain-number percentages, trimmed text), then runs the validators in
validators.py. Fields that fail to parse do not raise immediately: they are
recorded and normalization keeps going, so a single malformed field does not
hide other problems on the same order. If anything failed to parse or any
validator check fails, one aggregated ManualReviewRequired is raised instead
of returning a partially-trustworthy order - this is the fail-closed gate
the design doc requires before automation opens a New Order.
"""

from __future__ import annotations

import datetime
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.extraction.models import RawAddress, RawLineItem, RawOrder
from fakturama_automation.normalization import config
from fakturama_automation.normalization.models import NormalizedAddress, NormalizedLineItem, NormalizedOrder
from fakturama_automation.normalization.validators import (
    check_confidence,
    check_line_total,
    check_required_fields,
    recompute_line_total,
)

# ISO first (the canonical format Fakturama and this pipeline standardize
# on), with an unambiguous day-first fallback for the German-locale source
# documents this system targets. Anything else fails closed rather than
# being guessed (e.g. an ambiguous MM/DD vs DD/MM slash date).
_DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y"]

_CURRENCY_SYMBOLS = re.compile(r"[€$£]|\bEUR\b|\bUSD\b|\bGBP\b", re.IGNORECASE)


def normalize_order(
    raw_order: RawOrder,
    *,
    confidence_threshold: float = config.DEFAULT_CONFIDENCE_THRESHOLD,
    line_total_tolerance: Decimal = config.DEFAULT_LINE_TOTAL_TOLERANCE,
) -> NormalizedOrder:
    """Normalize a RawOrder into a NormalizedOrder, or raise ManualReviewRequired.

    Every parse failure and validator failure is collected before raising,
    so error_handling gets one specific, complete reason rather than the
    first problem found.
    """
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
    normalized = NormalizedLineItem(
        sku=_trim(item.sku),
        description=_trim(item.description),
        quantity=_parse_money(item.quantity, f"{prefix}.quantity", failures),
        unit_net_price=_parse_money(item.unit_net_price, f"{prefix}.unit_net_price", failures),
        vat_percent=_parse_percent(item.vat_percent, f"{prefix}.vat_percent", failures),
        discount=_parse_percent(item.discount, f"{prefix}.discount", failures),
        source_line_total=_parse_money(item.source_line_total, f"{prefix}.source_line_total", failures),
    )
    normalized.recomputed_total = recompute_line_total(normalized)
    return normalized


def _trim(value: str | None) -> str:
    return value.strip() if value else ""


def _parse_date(value: str | None, field_name: str, failures: list[str]) -> datetime.date | None:
    text = _trim(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    failures.append(f"{field_name}: unparseable date '{text}'")
    return None


def _normalize_numeric_text(text: str) -> str:
    """Normalize a number's decimal/thousands separators to plain dot
    notation. Handles dot-decimal (the source documents this system
    targets), European comma-decimal (a defensive fallback for the German
    Fakturama context), and thousands separators in either style.
    """
    cleaned = text.replace(" ", "").replace("\xa0", "")
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


def _parse_money(value: str | None, field_name: str, failures: list[str]) -> Decimal:
    text = _trim(value)
    if not text:
        return Decimal(0)
    cleaned = _normalize_numeric_text(_CURRENCY_SYMBOLS.sub("", text).strip())
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        failures.append(f"{field_name}: unparseable number '{text}'")
        return Decimal(0)
    return parsed.quantize(config.MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def _parse_percent(value: str | None, field_name: str, failures: list[str]) -> Decimal:
    text = _trim(value)
    if not text:
        return Decimal(0)
    cleaned = _normalize_numeric_text(text.replace("%", "").strip())
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        failures.append(f"{field_name}: unparseable percentage '{text}'")
        return Decimal(0)
