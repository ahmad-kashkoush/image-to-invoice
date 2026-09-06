
from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import locators, readers, screens
from fakturama_automation.verification import comparisons

_STEP = "verify_payment_applied"


def verify_payment_applied(invoice_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    problems = payment_problems(invoice_window, normalized_order)
    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True


def payment_problems(invoice_window: Any, normalized_order: NormalizedOrder) -> list[str]:
    problems: list[str] = []

    method_text = readers.field_value(locators.payment_method_combo(invoice_window))
    if not comparisons.text_equals(normalized_order.payment_method, method_text):
        problems.append(f"payment method: expected '{normalized_order.payment_method}', UI shows '{method_text}'")

    is_paid_expected = normalized_order.is_paid
    is_paid_ui = readers.read_toggle_state(invoice_window, name=screens.INVOICE_PAID_CHECKBOX_NAME)

    if is_paid_expected:
        if not is_paid_ui:
            problems.append("expected paid status PAID, but the paid checkbox is not checked")
        else:
            date_text = readers.field_value(locators.payment_date_edit(invoice_window))
            if not comparisons.date_equals(normalized_order.payment_date, date_text):
                problems.append(f"payment date: expected {normalized_order.payment_date}, UI shows '{date_text}'")
            value_text = readers.read_field_text(invoice_window, name=screens.INVOICE_PAYMENT_VALUE_EDIT_NAME)
            _, _, gross_total = comparisons.order_level_totals(normalized_order)
            if not comparisons.money_equals(gross_total, value_text):
                problems.append(f"Value: expected the full invoice total {gross_total}, UI shows '{value_text}'")
    elif is_paid_ui:
        problems.append("expected paid status not PAID, but the paid checkbox is checked")
        date_text = readers.field_value(locators.payment_date_edit(invoice_window))
        value_text = readers.read_field_text(invoice_window, name=screens.INVOICE_PAYMENT_VALUE_EDIT_NAME)
        if date_text.strip():
            problems.append(f"expected no payment date (status not PAID), UI shows '{date_text}'")
        if value_text.strip():
            problems.append(f"expected no Value (status not PAID), UI shows '{value_text}'")
    return problems
