"""Order verification, before and after the save.

`verify_order_before_save` is Task 4.1/4.3's check, made while the order can
still be fixed; `verify_order_saved` confirms the save persisted (an
assigned order number replaces "New Order" in the tab title) and that what
persisted still matches, lines included.

Every discrepancy is aggregated into one ManualReviewRequired rather than
raising on the first, so a reviewer sees the whole picture at once.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import screens
from fakturama_automation.verification import comparisons, readback

_STEP = "verify_order_saved"
# Matches state_machine.WorkflowState.VALIDATE_ORDER.value.
_BEFORE_SAVE_STEP = "validate_order"


def verify_order_before_save(order_window: Any, normalized_order: NormalizedOrder) -> bool:
    """Confirm the Order's order-level fields match the record *before*
    it is saved (Task 4.1/4.3).

    Fakturama computes Total Net / VAT / Total itself from the entered
    lines, so this compares its arithmetic against the record's. It is the
    first check that can catch a whole-order problem - a line that reached
    the grid but not the totals, a non-zero order-level discount or
    shipping charge, a pricing mode that reverted to Gross - none of which a
    per-line check can see.

    Deliberately not a re-read of the item grid: every line was already
    compared column by column right after entry, and that read is a vision
    call. Nor a re-run of normalization's validators, which ran on this same
    record before any UI action - what makes this state real is that it
    reads the UI, which normalization has never seen.

    Known gap: the addresses Task 4.1 also asks about are not read back (a
    multi-line Edit nobody has probed for read-back). See README's Next
    Steps.
    """
    problems = _field_problems(order_window, normalized_order)
    if problems:
        raise ManualReviewRequired(_BEFORE_SAVE_STEP, "; ".join(problems))
    return True


def verify_order_saved(order_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    """Confirm the Order in order_window was actually saved and its key
    fields match normalized_order.

    Returns True only if the Order is persisted (an assigned order number)
    and every checked field/line matches; otherwise raises
    ManualReviewRequired with every mismatch found, not just the first.
    """
    problems: list[str] = []

    title = readback.window_title(order_window)
    if not title or title == screens.ORDER_TAB_TITLE_UNSAVED:
        problems.append(f"no order number assigned yet (editor still titled {title!r})")

    problems.extend(_field_problems(order_window, normalized_order))
    problems.extend(_line_item_problems(order_window, normalized_order, client=client))

    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True


def _field_problems(order_window: Any, order: NormalizedOrder) -> list[str]:
    problems: list[str] = []

    cust_ref = readback.read_field_text(order_window, name=screens.ORDER_CUST_REF_EDIT_NAME)
    if not comparisons.text_equals(order.external_reference, cust_ref):
        problems.append(f"Cust.Ref.: expected '{order.external_reference}', UI shows '{cust_ref}'")

    net_total, vat_total, gross_total = comparisons.order_level_totals(order)

    total_net_text = readback.read_field_text(order_window, name=screens.ORDER_TOTAL_NET_EDIT_NAME)
    if not comparisons.money_equals(net_total, total_net_text):
        problems.append(f"Total Net: expected {net_total}, UI shows '{total_net_text}'")

    vat_text = readback.read_field_text(order_window, name=screens.ORDER_VAT_EDIT_NAME)
    if not comparisons.money_equals(vat_total, vat_text):
        problems.append(f"VAT: expected {vat_total}, UI shows '{vat_text}'")

    total_text = readback.read_field_text(order_window, name=screens.ORDER_TOTAL_EDIT_NAME)
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Total: expected {gross_total}, UI shows '{total_text}'")

    return problems


def _line_item_problems(order_window: Any, order: NormalizedOrder, *, client: Any) -> list[str]:
    rows = readback.read_grid(
        order_window,
        columns=screens.ITEMS_GRID_READ_COLUMNS,
        client=client,
    )

    problems: list[str] = []
    if len(rows) != len(order.line_items):
        problems.append(f"expected {len(order.line_items)} order line(s), UI grid shows {len(rows)}")

    for item, row in zip(order.line_items, rows):
        problems.extend(comparisons.line_row_problems(item, row))

    return problems
