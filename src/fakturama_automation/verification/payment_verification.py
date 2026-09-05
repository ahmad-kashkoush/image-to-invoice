"""Payment status fakturama_automation.verification.

Section 5 (verification). Reads the linked Invoice's payment fields back
after they were applied and compares them against the normalized order's
extracted payment_method/payment_status/payment_date (Task Description
5.2/5.3/5.6): the payment method must match; if the extracted status is
PAID, the paid toggle, payment date, and Value (the full invoice total)
must all be set correctly; if not PAID, paid must stay clear and no
date/value may have been invented.

The per-invoice payment-status controls (paid checkbox, payment date,
Value) were never captured by a VM probe - only the payment-*method*
"Term of Payment" form was (probes/probe-10-payment-create-form.txt).
verification/config.py's INVOICE_PAYMENT_METHOD_COMBO_NAME/
INVOICE_PAID_CHECKBOX_NAME/INVOICE_PAYMENT_DATE_EDIT_NAME/
INVOICE_PAYMENT_VALUE_EDIT_NAME are left as empty-string placeholders
rather than a guess: against a real window they fail closed
(ControlNotFoundError/AmbiguousControlError) until a VM probe session
fills them in - see Doc/adr/0004-verification.md.
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

    method_text = readback.read_field_text(
        invoice_window, control_type="ComboBox", name=config.INVOICE_PAYMENT_METHOD_COMBO_NAME
    )
    if not comparisons.text_equals(normalized_order.payment_method, method_text):
        problems.append(f"payment method: expected '{normalized_order.payment_method}', UI shows '{method_text}'")

    is_paid_expected = normalized_order.payment_status.strip().upper() == "PAID"
    is_paid_ui = readback.read_toggle_state(invoice_window, name=config.INVOICE_PAID_CHECKBOX_NAME)
    date_text = readback.read_field_text(invoice_window, name=config.INVOICE_PAYMENT_DATE_EDIT_NAME)
    value_text = readback.read_field_text(invoice_window, name=config.INVOICE_PAYMENT_VALUE_EDIT_NAME)

    if is_paid_expected:
        if not is_paid_ui:
            problems.append("expected paid status PAID, but the paid checkbox is not checked")
        if not comparisons.date_equals(normalized_order.payment_date, date_text):
            problems.append(f"payment date: expected {normalized_order.payment_date}, UI shows '{date_text}'")
        _, _, gross_total = comparisons.order_level_totals(normalized_order)
        if not comparisons.money_equals(gross_total, value_text):
            problems.append(f"Value: expected the full invoice total {gross_total}, UI shows '{value_text}'")
    else:
        if is_paid_ui:
            problems.append("expected paid status not PAID, but the paid checkbox is checked")
        if date_text.strip():
            problems.append(f"expected no payment date (status not PAID), UI shows '{date_text}'")
        if value_text.strip():
            problems.append(f"expected no Value (status not PAID), UI shows '{value_text}'")

    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True
