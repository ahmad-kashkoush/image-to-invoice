"""Payment status verification.

Reads the linked Invoice's payment fields back after they were applied and
compares them against the normalized order's extracted payment_method/
payment_status/payment_date: the payment method must match; if the
extracted status is PAID, the paid toggle, payment date, and Value (the
full invoice total) must all be set correctly; if not PAID, paid must stay
clear and no date/value may have been invented.

The payment-method combo and payment-date edit are blank-named, located
structurally via readback.payment_method_combo/payment_date_edit - the
same helpers orchestrator.actions.apply_payment uses to set them.

The date/Value fields don't exist in the UI tree at all until "paid" is
checked (readback.payment_details_pane), so this only reads them when the
checkbox is actually checked, never assuming they exist just because a
status was expected.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.verification import comparisons, config, readback

_STEP = "verify_payment_applied"


def verify_payment_applied(invoice_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    """Confirm payment status (and, if PAID, payment date and full value)
    were applied correctly to the Invoice.

    Returns True only if the payment method, paid toggle, and (when PAID)
    payment date and Value all match; otherwise raises
    ManualReviewRequired with every mismatch found, not just the first.
    """
    problems: list[str] = []

    method_text = readback.payment_method_combo(invoice_window).window_text()
    if not comparisons.text_equals(normalized_order.payment_method, method_text):
        problems.append(f"payment method: expected '{normalized_order.payment_method}', UI shows '{method_text}'")

    is_paid_expected = normalized_order.payment_status.strip().upper() == "PAID"
    is_paid_ui = readback.read_toggle_state(invoice_window, name=config.INVOICE_PAID_CHECKBOX_NAME)

    if is_paid_expected:
        if not is_paid_ui:
            problems.append("expected paid status PAID, but the paid checkbox is not checked")
        else:
            date_text = readback.payment_date_edit(invoice_window).window_text()
            if not comparisons.date_equals(normalized_order.payment_date, date_text):
                problems.append(f"payment date: expected {normalized_order.payment_date}, UI shows '{date_text}'")
            value_text = readback.read_field_text(invoice_window, name=config.INVOICE_PAYMENT_VALUE_EDIT_NAME)
            _, _, gross_total = comparisons.order_level_totals(normalized_order)
            if not comparisons.money_equals(gross_total, value_text):
                problems.append(f"Value: expected the full invoice total {gross_total}, UI shows '{value_text}'")
    elif is_paid_ui:
        problems.append("expected paid status not PAID, but the paid checkbox is checked")
        date_text = readback.payment_date_edit(invoice_window).window_text()
        value_text = readback.read_field_text(invoice_window, name=config.INVOICE_PAYMENT_VALUE_EDIT_NAME)
        if date_text.strip():
            problems.append(f"expected no payment date (status not PAID), UI shows '{date_text}'")
        if value_text.strip():
            problems.append(f"expected no Value (status not PAID), UI shows '{value_text}'")
    # else: not paid expected, not paid in the UI - the date/Value fields
    # don't exist in this state at all (see this module's own docstring),
    # so their absence already is "nothing was invented" - nothing more to
    # check.

    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True
