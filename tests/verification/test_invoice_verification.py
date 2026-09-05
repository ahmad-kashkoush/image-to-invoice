"""Tests for verification.invoice_verification.verify_invoice_matches_order.

Same fake style as test_order_verification.py - no real window, no
screenshot, no network. Uses the golden sample order's numbers
(WEB-2026-0714-A17, Northstar Office GmbH).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.verification import config
from fakturama_automation.verification.invoice_verification import verify_invoice_matches_order


class _FakeControl:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def window_text(self) -> str:
        return self._text

    def capture_as_image(self):
        return _FakeImage()


class _FakeImage:
    def save(self, buffer, format=None) -> None:  # noqa: A002 - matches PIL's Image.save signature
        buffer.write(b"fake-png-bytes")


class _FakeInvoiceWindow:
    def __init__(self, registry: dict[tuple, _FakeControl]) -> None:
        self._registry = registry

    def children(self, control_type=None, title=None, auto_id=None):
        control = self._registry.get((control_type, title, auto_id))
        return [control] if control is not None else []


class _FakeMessages:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def create(self, **kwargs):
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", name="record_grid_rows", input={"rows": self._rows})],
        )


class _FakeVisionClient:
    def __init__(self, rows: list[dict]) -> None:
        self.messages = _FakeMessages(rows)


def _golden_order() -> NormalizedOrder:
    line1 = NormalizedLineItem(
        sku="CHR-ERG-01",
        description="Ergonomic Desk Chair",
        quantity=Decimal("2"),
        unit_net_price=Decimal("250.00"),
        vat_percent=Decimal("19"),
        discount=Decimal("10"),
        source_line_total=Decimal("450.00"),
        recomputed_total=Decimal("450.00"),
    )
    line2 = NormalizedLineItem(
        sku="MAT-DESK-02",
        description="Anti-Fatigue Desk Mat",
        quantity=Decimal("3"),
        unit_net_price=Decimal("40.00"),
        vat_percent=Decimal("19"),
        discount=Decimal("0"),
        source_line_total=Decimal("120.00"),
        recomputed_total=Decimal("120.00"),
    )
    return NormalizedOrder(external_reference="WEB-2026-0714-A17", line_items=[line1, line2])


def _golden_rows() -> list[dict]:
    return [
        {"SKU": "CHR-ERG-01", "Qty.": "2", "U.Price": "250.00", "VAT": "19", "Discount": "10", "Price": "450.00"},
        {"SKU": "MAT-DESK-02", "Qty.": "3", "U.Price": "40.00", "VAT": "19", "Discount": "0", "Price": "120.00"},
    ]


def _registry(*, cust_ref="WEB-2026-0714-A17", total="678.30") -> dict:
    return {
        ("Edit", config.INVOICE_CUST_REF_EDIT_NAME, None): _FakeControl(cust_ref),
        ("Edit", config.INVOICE_TOTAL_EDIT_NAME, None): _FakeControl(total),
        ("Pane", None, config.INVOICE_ITEMS_GRID_PANE_AUTO_ID): _FakeControl(),
    }


def test_returns_true_when_invoice_fields_match_the_order() -> None:
    window = _FakeInvoiceWindow(_registry())
    client = _FakeVisionClient(rows=_golden_rows())

    assert verify_invoice_matches_order(window, _golden_order(), client=client) is True


def test_raises_when_cust_ref_was_not_copied_correctly() -> None:
    window = _FakeInvoiceWindow(_registry(cust_ref="SOME-OTHER-REF"))
    client = _FakeVisionClient(rows=_golden_rows())

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_invoice_matches_order(window, _golden_order(), client=client)

    assert exc_info.value.step == "verify_invoice_matches_order"
    assert "Cust.Ref." in exc_info.value.reason


def test_raises_when_total_was_not_copied_correctly() -> None:
    window = _FakeInvoiceWindow(_registry(total="0.00"))
    client = _FakeVisionClient(rows=_golden_rows())

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_invoice_matches_order(window, _golden_order(), client=client)

    assert "Total" in exc_info.value.reason


def test_raises_when_a_line_item_was_not_copied_correctly() -> None:
    window = _FakeInvoiceWindow(_registry())
    rows = _golden_rows()
    rows[1]["Price"] = "1.00"
    client = _FakeVisionClient(rows=rows)

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_invoice_matches_order(window, _golden_order(), client=client)

    assert "MAT-DESK-02" in exc_info.value.reason


def test_aggregates_every_problem_into_one_exception() -> None:
    window = _FakeInvoiceWindow(_registry(cust_ref="WRONG", total="0.00"))
    client = _FakeVisionClient(rows=_golden_rows()[:1])

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_invoice_matches_order(window, _golden_order(), client=client)

    reason = exc_info.value.reason
    assert "Cust.Ref." in reason
    assert "Total" in reason
    assert "expected 2 invoice line(s), UI grid shows 1" in reason
