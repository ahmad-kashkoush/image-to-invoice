from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import readers, screens
from fakturama_automation.verification import comparisons
from fakturama_automation.verification.payment_verification import payment_problems

_STEP = "verify_invoice_matches_order"
_SAVED_STEP = "verify_invoice_saved"


def verify_invoice_matches_order(invoice_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    problems: list[str] = []

    cust_ref = readers.read_field_text(invoice_window, name=screens.INVOICE_CUST_REF_EDIT_NAME)
    if not comparisons.text_equals(normalized_order.external_reference, cust_ref):
        problems.append(f"Cust.Ref.: expected '{normalized_order.external_reference}', UI shows '{cust_ref}'")

    _, _, gross_total = comparisons.order_level_totals(normalized_order)
    total_text = readers.read_field_text(invoice_window, name=screens.INVOICE_TOTAL_EDIT_NAME)
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Total: expected {gross_total}, UI shows '{total_text}'")

    rows = readers.read_items_grid(
        invoice_window,
        columns=screens.ITEMS_GRID_READ_COLUMNS,
        client=client,
    )
    if len(rows) != len(normalized_order.line_items):
        problems.append(f"expected {len(normalized_order.line_items)} invoice line(s), UI grid shows {len(rows)}")
    for item, row in zip(normalized_order.line_items, rows):
        problems.extend(comparisons.line_row_problems(item, row))

    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True


def verify_invoice_saved(invoice_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    problems: list[str] = []

    title = readers.window_title(invoice_window)
    if not title or title == screens.INVOICE_TAB_TITLE_UNSAVED:
        problems.append(f"no invoice number assigned yet (editor still titled {title!r})")

    cust_ref = readers.read_field_text(invoice_window, name=screens.INVOICE_CUST_REF_EDIT_NAME)
    if not comparisons.text_equals(normalized_order.external_reference, cust_ref):
        problems.append(f"Cust.Ref.: expected '{normalized_order.external_reference}', UI shows '{cust_ref}'")

    _, _, gross_total = comparisons.order_level_totals(normalized_order)
    total_text = readers.read_field_text(invoice_window, name=screens.INVOICE_TOTAL_EDIT_NAME)
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Total: expected {gross_total}, UI shows '{total_text}'")

    problems.extend(payment_problems(invoice_window, normalized_order))

    if problems:
        raise ManualReviewRequired(_SAVED_STEP, "; ".join(problems))
    return True
