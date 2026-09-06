from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.extraction.models import RawAddress, RawLineItem, RawOrder
from fakturama_automation.normalization.normalizer import normalize_order

HIGH_CONF = 0.95

ADDR_CONF = {"street": HIGH_CONF, "postal_code": HIGH_CONF, "city": HIGH_CONF, "country": HIGH_CONF}
LINE_CONF = {
    "sku": HIGH_CONF,
    "description": HIGH_CONF,
    "quantity": HIGH_CONF,
    "unit_net_price": HIGH_CONF,
    "vat_percent": HIGH_CONF,
    "discount": HIGH_CONF,
    "source_line_total": HIGH_CONF,
}
ORDER_CONF = {
    "order_date": HIGH_CONF,
    "external_reference": HIGH_CONF,
    "debtor_company_name": HIGH_CONF,
    "contact_name": HIGH_CONF,
    "alias": HIGH_CONF,
    "payment_details": HIGH_CONF,
    "payment_method": HIGH_CONF,
    "payment_status": HIGH_CONF,
    "payment_date": HIGH_CONF,
}


def _golden_raw_order(**overrides) -> RawOrder:
    defaults = dict(
        source_image_path="/orders/WEB-2026-0714-A17.png",
        order_date="2026-07-14",
        external_reference="WEB-2026-0714-A17",
        debtor_company_name=" Northstar Office GmbH ",
        contact_name="Marta Klein",
        alias="NORTHSTAR-BERLIN",
        billing_address=RawAddress(
            raw_text="Northstar Office GmbH, Friedrichstrasse 88, 10117 Berlin, Germany",
            street="Friedrichstrasse 88",
            postal_code="10117",
            city="Berlin",
            country="Germany",
            confidence=dict(ADDR_CONF),
        ),
        delivery_address=RawAddress(
            raw_text="Northstar Office Warehouse, Beusselstrasse 44, 10553 Berlin, Germany",
            street="Beusselstrasse 44",
            postal_code="10553",
            city="Berlin",
            country="Germany",
            confidence=dict(ADDR_CONF),
        ),
        payment_details=None,
        payment_method="Bank Transfer",
        payment_status="PAID",
        payment_date="2026-07-18",
        line_items=[
            RawLineItem(
                sku="CHR-ERG-01",
                description="Ergonomic Desk Chair",
                quantity="2",
                unit_net_price="250.00",
                vat_percent="19",
                discount="10",
                source_line_total="450.00",
                confidence=dict(LINE_CONF),
            ),
            RawLineItem(
                sku="MAT-DESK-02",
                description="Anti-Fatigue Desk Mat",
                quantity="3",
                unit_net_price="40.00",
                vat_percent="19",
                discount="0",
                source_line_total="120.00",
                confidence=dict(LINE_CONF),
            ),
        ],
        confidence=dict(ORDER_CONF),
    )
    defaults.update(overrides)
    return RawOrder(**defaults)


def test_golden_sample_order_normalizes_cleanly() -> None:
    order = normalize_order(_golden_raw_order())

    assert order.order_date == datetime.date(2026, 7, 14)
    assert order.payment_date == datetime.date(2026, 7, 18)
    assert order.debtor_company_name == "Northstar Office GmbH"  # trimmed
    assert order.payment_status == "PAID"
    assert order.billing_address.city == "Berlin"
    assert order.delivery_address.postal_code == "10553"

    assert len(order.line_items) == 2
    chair, mat = order.line_items
    assert chair.recomputed_total == Decimal("450.00")
    assert mat.recomputed_total == Decimal("120.00")
    assert chair.discount == Decimal("10")
    assert chair.vat_percent == Decimal("19")

    net_total = sum((item.recomputed_total for item in order.line_items), Decimal(0))
    assert net_total == Decimal("570.00")


def test_dotted_date_is_accepted_as_fallback() -> None:
    order = normalize_order(_golden_raw_order(order_date="14.07.2026"))
    assert order.order_date == datetime.date(2026, 7, 14)


def test_ambiguous_unparseable_date_raises_manual_review() -> None:
    with pytest.raises(ManualReviewRequired):
        normalize_order(_golden_raw_order(order_date="not a date"))


def test_missing_optional_date_is_none_not_a_failure() -> None:
    order = normalize_order(_golden_raw_order(payment_date=None, payment_status="UNPAID"))
    assert order.payment_date is None


def test_european_comma_decimal_money_is_parsed() -> None:
    raw = _golden_raw_order()
    raw.line_items[0].unit_net_price = "250,00"
    raw.line_items[0].source_line_total = "450,00"
    order = normalize_order(raw)
    assert order.line_items[0].unit_net_price == Decimal("250.00")
    assert order.line_items[0].recomputed_total == Decimal("450.00")


def test_currency_symbol_and_thousands_separator_are_stripped() -> None:
    raw = _golden_raw_order()
    raw.line_items[0].quantity = "2"
    raw.line_items[0].unit_net_price = "EUR 1,250.00"
    raw.line_items[0].source_line_total = "2,250.00"
    order = normalize_order(raw)
    assert order.line_items[0].unit_net_price == Decimal("1250.00")


def test_line_total_mismatch_raises_manual_review() -> None:
    raw = _golden_raw_order()
    raw.line_items[0].source_line_total = "999.00"
    with pytest.raises(ManualReviewRequired) as exc_info:
        normalize_order(raw)
    assert "line 1" in str(exc_info.value)


def test_missing_debtor_name_raises_manual_review() -> None:
    with pytest.raises(ManualReviewRequired):
        normalize_order(_golden_raw_order(debtor_company_name=None))


def test_no_line_items_raises_manual_review() -> None:
    with pytest.raises(ManualReviewRequired):
        normalize_order(_golden_raw_order(line_items=[]))


def test_missing_sku_raises_manual_review() -> None:
    raw = _golden_raw_order()
    raw.line_items[0].sku = None
    with pytest.raises(ManualReviewRequired):
        normalize_order(raw)


def test_low_confidence_extracted_field_raises_manual_review() -> None:
    raw = _golden_raw_order()
    raw.confidence["debtor_company_name"] = 0.2
    with pytest.raises(ManualReviewRequired):
        normalize_order(raw)


def test_multiple_failures_are_aggregated_into_one_exception() -> None:
    raw = _golden_raw_order(debtor_company_name=None)
    raw.line_items[0].source_line_total = "999.00"
    with pytest.raises(ManualReviewRequired) as exc_info:
        normalize_order(raw)
    reason = str(exc_info.value)
    assert "required fields" in reason
    assert "line 1" in reason
