"""Invoice creation verification.

The linked Invoice is created directly from the saved Order, so its
Cust.Ref., item lines, and totals should already match the normalized
record - but this re-verifies that independently against the live UI
rather than trusting Fakturama's own Invoice-generation step, the same
fail-closed principle order_verification.py applies to the save step.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.verification import comparisons, config, readback

_STEP = "verify_invoice_matches_order"


def verify_invoice_matches_order(invoice_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    """Confirm the created Invoice's Cust.Ref., total, and item lines match
    normalized_order.

    Returns True only if every checked field/line matches; otherwise
    raises ManualReviewRequired with every mismatch found, not just the
    first.
    """
    problems: list[str] = []

    cust_ref = readback.read_field_text(invoice_window, name=config.INVOICE_CUST_REF_EDIT_NAME)
    if not comparisons.text_equals(normalized_order.external_reference, cust_ref):
        problems.append(f"Cust.Ref.: expected '{normalized_order.external_reference}', UI shows '{cust_ref}'")

    _, _, gross_total = comparisons.order_level_totals(normalized_order)
    total_text = readback.read_field_text(invoice_window, name=config.INVOICE_TOTAL_EDIT_NAME)
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Total: expected {gross_total}, UI shows '{total_text}'")

    rows = readback.read_grid(
        invoice_window,
        columns=config.INVOICE_ITEMS_GRID_COLUMNS,
        client=client,
        step=_STEP,
    )
    if len(rows) != len(normalized_order.line_items):
        problems.append(f"expected {len(normalized_order.line_items)} invoice line(s), UI grid shows {len(rows)}")
    for item, row in zip(normalized_order.line_items, rows):
        problems.extend(comparisons.line_row_problems(item, row))

    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True
