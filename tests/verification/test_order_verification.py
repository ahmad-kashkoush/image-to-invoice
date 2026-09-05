"""Tests for verification.order_verification.verify_order_saved.

Duck-typed fakes for the pywinauto window/control objects (same style as
tests/entity_resolution/test_debtor.py) and a fake anthropic-compatible
vision client (same style as tests/ui_automation/test_vision_grounding.py) -
no real window, no screenshot, no network. Uses the golden sample order's
numbers (WEB-2026-0714-A17, Northstar Office GmbH - see
comparisons_test's docstring) as the "known good" fixture.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.verification import config
from fakturama_automation.verification.order_verification import verify_order_saved


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


class _FakeOrderWindow:
    """children() looks a control up by the exact (control_type, title,
    auto_id) triple find_control passes through; window_text() returns
    this editor pane's own title, mutable to simulate "New Order" before
    a save vs. an assigned order number after one.
    """

    def __init__(self, title: str, registry: dict[tuple, _FakeControl]) -> None:
        self._title = title
        self._registry = registry

    def window_text(self) -> str:
        return self._title

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


def _registry(*, cust_ref="WEB-2026-0714-A17", total_net="570.00", vat="108.30", total="678.30") -> dict:
    return {
        ("Edit", config.ORDER_CUST_REF_EDIT_NAME, None): _FakeControl(cust_ref),
        ("Edit", config.ORDER_TOTAL_GROSS_EDIT_NAME, None): _FakeControl(total_net),
        ("Edit", config.ORDER_VAT_EDIT_NAME, None): _FakeControl(vat),
        ("Edit", config.ORDER_TOTAL_EDIT_NAME, None): _FakeControl(total),
        ("Pane", None, config.ORDER_ITEMS_GRID_PANE_AUTO_ID): _FakeControl(),
    }


def test_returns_true_when_order_saved_and_every_field_matches() -> None:
    window = _FakeOrderWindow("PO000001", _registry())
    client = _FakeVisionClient(rows=_golden_rows())

    assert verify_order_saved(window, _golden_order(), client=client) is True


def test_raises_when_order_number_not_yet_assigned() -> None:
    window = _FakeOrderWindow(config.ORDER_TAB_TITLE_UNSAVED, _registry())
    client = _FakeVisionClient(rows=_golden_rows())

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_order_saved(window, _golden_order(), client=client)

    assert exc_info.value.step == "verify_order_saved"
    assert "no order number" in exc_info.value.reason


def test_raises_when_cust_ref_does_not_match() -> None:
    window = _FakeOrderWindow("PO000001", _registry(cust_ref="SOME-OTHER-REF"))
    client = _FakeVisionClient(rows=_golden_rows())

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_order_saved(window, _golden_order(), client=client)

    assert "Cust.Ref." in exc_info.value.reason


def test_raises_when_total_does_not_match_source_totals() -> None:
    window = _FakeOrderWindow("PO000001", _registry(total="999.99"))
    client = _FakeVisionClient(rows=_golden_rows())

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_order_saved(window, _golden_order(), client=client)

    assert "Total" in exc_info.value.reason


def test_raises_when_line_count_does_not_match() -> None:
    window = _FakeOrderWindow("PO000001", _registry())
    client = _FakeVisionClient(rows=_golden_rows()[:1])

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_order_saved(window, _golden_order(), client=client)

    assert "expected 2 order line(s), UI grid shows 1" in exc_info.value.reason


def test_raises_when_a_line_field_does_not_match() -> None:
    window = _FakeOrderWindow("PO000001", _registry())
    rows = _golden_rows()
    rows[0]["Qty."] = "99"
    client = _FakeVisionClient(rows=rows)

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_order_saved(window, _golden_order(), client=client)

    assert "Qty." in exc_info.value.reason


def test_aggregates_every_problem_into_one_exception() -> None:
    window = _FakeOrderWindow(config.ORDER_TAB_TITLE_UNSAVED, _registry(cust_ref="WRONG", total="0.00"))
    client = _FakeVisionClient(rows=_golden_rows()[:1])

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_order_saved(window, _golden_order(), client=client)

    reason = exc_info.value.reason
    assert "no order number" in reason
    assert "Cust.Ref." in reason
    assert "Total" in reason
    assert "expected 2 order line(s), UI grid shows 1" in reason
