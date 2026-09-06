"""Invoice creation and save verification.

The linked Invoice is created directly from the saved Order, so its
Cust.Ref., item lines, and totals should already match the normalized
record - but this re-verifies that independently against the live UI
rather than trusting Fakturama's own Invoice-generation step, the same
fail-closed principle order_verification.py applies to the save step.

verify_invoice_saved covers the step after that: the Invoice's payment
fields are only typed into an open editor, and an editor's contents are
not the database. Confirmed live that a run which applied and verified
payment correctly still left no Invoice row persisted at all - the
document only reached the database when a human saved it by hand. So the
save is its own state with its own verification, exactly like the Order's.
"""

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
    """Confirm the created Invoice's Cust.Ref., total, and item lines match
    normalized_order.

    Returns True only if every checked field/line matches; otherwise
    raises ManualReviewRequired with every mismatch found, not just the
    first.
    """
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
    """Confirm the Invoice in invoice_window was actually persisted and
    that the payment fields survived the save.

    Returns True only if the Invoice has an assigned invoice number, its
    Cust.Ref./Total still match, and every payment field still reads back
    correctly; otherwise raises ManualReviewRequired with every mismatch
    found, not just the first.

    Deliberately does not re-read the item grid the way
    verify_invoice_matches_order does: that read is a vision call, the
    lines were verified against this same record moments earlier in the
    preceding state, and a save is not a line-editing operation. The Total
    field is the aggregate signal that would catch a line the save somehow
    changed - so this checks the things the *save* is responsible for
    (persistence, and that the just-applied payment data went with it),
    not everything already established before it. `client` is accepted for
    calling-convention symmetry with the other verifiers; unused here for
    that reason.
    """
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
