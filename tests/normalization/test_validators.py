from __future__ import annotations

from decimal import Decimal

from fakturama_automation.extraction.models import RawAddress, RawLineItem, RawOrder
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.normalization.validators import (
    check_confidence,
    check_line_total,
    check_required_fields,
    recompute_line_total,
)

TOLERANCE = Decimal("0.01")


def _line(**overrides) -> NormalizedLineItem:
    defaults = dict(
        sku="CHR-ERG-01",
        description="Ergonomic Desk Chair",
        quantity=Decimal("2"),
        unit_net_price=Decimal("250.00"),
        vat_percent=Decimal("19"),
        discount=Decimal("10"),
        source_line_total=Decimal("450.00"),
    )
    defaults.update(overrides)
    item = NormalizedLineItem(**defaults)
    return item


def _order(**overrides) -> NormalizedOrder:
    defaults = dict(debtor_company_name="Northstar Office GmbH", line_items=[_line()])
    defaults.update(overrides)
    return NormalizedOrder(**defaults)


# -- recompute_line_total / check_line_total --------------------------------


def test_recompute_line_total_applies_percentage_discount_and_excludes_vat() -> None:
    # Task rule 3.16: qty x unit_net x (1 - discount / 100); VAT is not part
    # of the net line total. From the sample order: 2 x 250.00 x 0.90 = 450.00.
    item = _line()
    # Both the named function and the model property, which must agree:
    # the function delegates to the property, so this pins that they do.
    assert recompute_line_total(item) == Decimal("450.00")
    assert item.recomputed_total == Decimal("450.00")


def test_recomputed_total_is_computed_not_assigned() -> None:
    # A line item built without going through the normalizer still has a
    # correct net total - every order-level total in the system derives
    # from it, so a default of 0 would silently understate an invoice.
    item = NormalizedLineItem(
        sku="CHR-ERG-01",
        quantity=Decimal("2"),
        unit_net_price=Decimal("250.00"),
        discount=Decimal("10"),
    )
    assert item.recomputed_total == Decimal("450.00")


def test_recompute_line_total_zero_discount() -> None:
    item = _line(quantity=Decimal("3"), unit_net_price=Decimal("40.00"), discount=Decimal("0"), source_line_total=Decimal("120.00"))
    assert item.recomputed_total == Decimal("120.00")


def test_check_line_total_passes_within_tolerance() -> None:
    item = _line()
    assert check_line_total(item, TOLERANCE) is True


def test_check_line_total_fails_on_mismatch() -> None:
    item = _line(source_line_total=Decimal("999.00"))
    assert check_line_total(item, TOLERANCE) is False


def test_check_line_total_within_tolerance_boundary() -> None:
    item = _line(source_line_total=Decimal("450.01"))
    assert check_line_total(item, TOLERANCE) is True


# -- check_required_fields ---------------------------------------------------


def test_check_required_fields_passes_with_debtor_and_line_item() -> None:
    assert check_required_fields(_order()) is True


def test_check_required_fields_fails_without_debtor_name() -> None:
    assert check_required_fields(_order(debtor_company_name="")) is False


def test_check_required_fields_fails_without_line_items() -> None:
    assert check_required_fields(_order(line_items=[])) is False


def test_check_required_fields_fails_without_sku() -> None:
    assert check_required_fields(_order(line_items=[_line(sku="")])) is False


def test_check_required_fields_fails_on_zero_quantity() -> None:
    assert check_required_fields(_order(line_items=[_line(quantity=Decimal("0"))])) is False


# -- check_confidence ---------------------------------------------------------


def _raw_order(**overrides) -> RawOrder:
    defaults = dict(
        debtor_company_name="Northstar Office GmbH",
        confidence={"debtor_company_name": 0.95},
    )
    defaults.update(overrides)
    return RawOrder(**defaults)


def test_check_confidence_passes_when_extracted_fields_are_confident() -> None:
    assert check_confidence(_raw_order(), 0.75) is True


def test_check_confidence_fails_when_extracted_field_is_low_confidence() -> None:
    order = _raw_order(confidence={"debtor_company_name": 0.2})
    assert check_confidence(order, 0.75) is False


def test_check_confidence_ignores_fields_never_extracted() -> None:
    # alias was never read off the document (None) - no confidence was
    # reported for it, and that must not fail the order.
    order = _raw_order(alias=None, confidence={"debtor_company_name": 0.95})
    assert check_confidence(order, 0.75) is True


def test_check_confidence_treats_missing_confidence_key_as_zero_for_extracted_field() -> None:
    # debtor_company_name was extracted (non-empty) but no confidence key
    # was reported for it - must fail closed (treated as 0.0), not pass.
    order = RawOrder(debtor_company_name="Northstar Office GmbH", confidence={})
    assert check_confidence(order, 0.75) is False


def test_check_confidence_checks_address_and_line_item_fields() -> None:
    order = RawOrder(
        debtor_company_name="Northstar Office GmbH",
        confidence={"debtor_company_name": 0.95},
        billing_address=RawAddress(city="Berlin", confidence={"city": 0.1}),
        line_items=[RawLineItem(sku="SKU1", confidence={"sku": 0.9})],
    )
    assert check_confidence(order, 0.75) is False
