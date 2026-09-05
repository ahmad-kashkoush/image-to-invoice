"""Tests for verification.payment_verification.verify_payment_applied.

Same fake style as test_order_verification.py, plus a get_toggle_state()
on the fake control for the paid checkbox (pywinauto's documented UIA
TogglePattern wrapper method).

The Invoice's payment-status controls (paid checkbox, payment date,
Value) have no VM-probed selector yet - verification/config.py leaves
INVOICE_PAID_CHECKBOX_NAME/INVOICE_PAYMENT_DATE_EDIT_NAME/
INVOICE_PAYMENT_VALUE_EDIT_NAME as empty-string placeholders (see that
module's docstring and Doc/adr/0004-verification.md). An autouse fixture
here monkeypatches them to distinct assumed names for the duration of
this file's tests, purely so the fakes below can address each field
independently; verify_payment_applied itself is unchanged production
code reading whatever verification/config.py holds at call time, and
against a real (un-probed) window still fails closed exactly as
documented.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.verification import config
from fakturama_automation.verification.payment_verification import verify_payment_applied


@pytest.fixture(autouse=True)
def _assumed_payment_selectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "INVOICE_PAYMENT_METHOD_COMBO_NAME", "Payment method")
    monkeypatch.setattr(config, "INVOICE_PAID_CHECKBOX_NAME", "Paid")
    monkeypatch.setattr(config, "INVOICE_PAYMENT_DATE_EDIT_NAME", "Payment date")
    monkeypatch.setattr(config, "INVOICE_PAYMENT_VALUE_EDIT_NAME", "Value")


class _FakeControl:
    def __init__(self, text: str = "", *, toggled: bool = False) -> None:
        self._text = text
        self._toggled = toggled

    def window_text(self) -> str:
        return self._text

    def get_toggle_state(self) -> int:
        return 1 if self._toggled else 0


class _FakeInvoiceWindow:
    def __init__(self, registry: dict[tuple, _FakeControl]) -> None:
        self._registry = registry

    def descendants(self, control_type=None, title=None, auto_id=None):
        control = self._registry.get((control_type, title, auto_id))
        return [control] if control is not None else []


def _golden_order(*, payment_status: str = "PAID") -> NormalizedOrder:
    line = NormalizedLineItem(
        sku="CHR-ERG-01",
        quantity=Decimal("2"),
        unit_net_price=Decimal("250.00"),
        vat_percent=Decimal("19"),
        discount=Decimal("10"),
        source_line_total=Decimal("450.00"),
        recomputed_total=Decimal("450.00"),
    )
    import datetime

    return NormalizedOrder(
        payment_method="Bank Transfer",
        payment_status=payment_status,
        payment_date=datetime.date(2026, 7, 18) if payment_status == "PAID" else None,
        line_items=[line],
    )


def _paid_registry(*, method="Bank Transfer", paid=True, date="2026-07-18", value="535.50") -> dict:
    return {
        ("ComboBox", "Payment method", None): _FakeControl(method),
        ("CheckBox", "Paid", None): _FakeControl(toggled=paid),
        ("Edit", "Payment date", None): _FakeControl(date),
        ("Edit", "Value", None): _FakeControl(value),
    }


def _unpaid_registry(*, method="Bank Transfer", paid=False, date="", value="") -> dict:
    return {
        ("ComboBox", "Payment method", None): _FakeControl(method),
        ("CheckBox", "Paid", None): _FakeControl(toggled=paid),
        ("Edit", "Payment date", None): _FakeControl(date),
        ("Edit", "Value", None): _FakeControl(value),
    }


# 450.00 net + 19% VAT (85.50) = 535.50 gross, for the single-line order above.


def test_returns_true_for_a_matching_paid_invoice() -> None:
    window = _FakeInvoiceWindow(_paid_registry())

    assert verify_payment_applied(window, _golden_order(payment_status="PAID")) is True


def test_returns_true_for_a_matching_unpaid_invoice() -> None:
    window = _FakeInvoiceWindow(_unpaid_registry())

    assert verify_payment_applied(window, _golden_order(payment_status="")) is True


def test_raises_when_payment_method_does_not_match() -> None:
    window = _FakeInvoiceWindow(_paid_registry(method="Credit Card"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status="PAID"))

    assert exc_info.value.step == "verify_payment_applied"
    assert "payment method" in exc_info.value.reason


def test_raises_when_paid_expected_but_checkbox_not_checked() -> None:
    window = _FakeInvoiceWindow(_paid_registry(paid=False))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status="PAID"))

    assert "paid checkbox is not checked" in exc_info.value.reason


def test_raises_when_payment_date_does_not_match() -> None:
    window = _FakeInvoiceWindow(_paid_registry(date="2026-01-01"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status="PAID"))

    assert "payment date" in exc_info.value.reason


def test_raises_when_value_does_not_match_full_invoice_total() -> None:
    window = _FakeInvoiceWindow(_paid_registry(value="0.00"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status="PAID"))

    assert "Value" in exc_info.value.reason


def test_raises_when_not_paid_but_checkbox_is_checked() -> None:
    window = _FakeInvoiceWindow(_unpaid_registry(paid=True))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status=""))

    assert "checkbox is checked" in exc_info.value.reason


def test_raises_when_not_paid_but_a_payment_date_was_invented() -> None:
    window = _FakeInvoiceWindow(_unpaid_registry(date="2026-07-18"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status=""))

    assert "no payment date" in exc_info.value.reason


def test_raises_when_not_paid_but_a_value_was_invented() -> None:
    window = _FakeInvoiceWindow(_unpaid_registry(value="535.50"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status=""))

    assert "no Value" in exc_info.value.reason


def test_aggregates_every_problem_into_one_exception() -> None:
    window = _FakeInvoiceWindow(_paid_registry(method="Credit Card", paid=False, date="2026-01-01", value="0.00"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        verify_payment_applied(window, _golden_order(payment_status="PAID"))

    reason = exc_info.value.reason
    assert "payment method" in reason
    assert "paid checkbox is not checked" in reason
    assert "payment date" in reason
    assert "Value" in reason
