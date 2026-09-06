"""Order save verification.

Reads the saved Order's own state back from the live UI rather than
trusting the save action succeeded: the editor's own tab title (an
assigned order number replaces "New Order" once saved), its Cust.Ref./
Total Gross/Discount/VAT/Total fields, and its item-row grid
(vision-grounded - Fakturama's line grid has no UIA rows).

Every discrepancy found is aggregated into one ManualReviewRequired rather
than raising on the first problem, so a reviewer sees the whole picture at
once.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.verification import comparisons, config, readback

_STEP = "verify_order_saved"


def verify_order_saved(order_window: Any, normalized_order: NormalizedOrder, *, client: Any = None) -> bool:
    """Confirm the Order in order_window was actually saved and its key
    fields match normalized_order.

    Returns True only if the Order is persisted (an assigned order number)
    and every checked field/line matches; otherwise raises
    ManualReviewRequired with every mismatch found, not just the first.
    """
    problems: list[str] = []

    title = readback.window_title(order_window)
    if not title or title == config.ORDER_TAB_TITLE_UNSAVED:
        problems.append(f"no order number assigned yet (editor still titled {title!r})")

    problems.extend(_field_problems(order_window, normalized_order))
    problems.extend(_line_item_problems(order_window, normalized_order, client=client))

    if problems:
        raise ManualReviewRequired(_STEP, "; ".join(problems))
    return True


def _field_problems(order_window: Any, order: NormalizedOrder) -> list[str]:
    problems: list[str] = []

    cust_ref = readback.read_field_text(order_window, name=config.ORDER_CUST_REF_EDIT_NAME)
    if not comparisons.text_equals(order.external_reference, cust_ref):
        problems.append(f"Cust.Ref.: expected '{order.external_reference}', UI shows '{cust_ref}'")

    net_total, vat_total, gross_total = comparisons.order_level_totals(order)

    total_net_text = readback.read_field_text(order_window, name=config.ORDER_TOTAL_NET_EDIT_NAME)
    if not comparisons.money_equals(net_total, total_net_text):
        problems.append(f"Total Net: expected {net_total}, UI shows '{total_net_text}'")

    vat_text = readback.read_field_text(order_window, name=config.ORDER_VAT_EDIT_NAME)
    if not comparisons.money_equals(vat_total, vat_text):
        problems.append(f"VAT: expected {vat_total}, UI shows '{vat_text}'")

    total_text = readback.read_field_text(order_window, name=config.ORDER_TOTAL_EDIT_NAME)
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Total: expected {gross_total}, UI shows '{total_text}'")

    return problems


def _line_item_problems(order_window: Any, order: NormalizedOrder, *, client: Any) -> list[str]:
    rows = readback.read_grid(
        order_window,
        columns=config.ORDER_ITEMS_GRID_COLUMNS,
        client=client,
        step=_STEP,
    )

    problems: list[str] = []
    if len(rows) != len(order.line_items):
        problems.append(f"expected {len(order.line_items)} order line(s), UI grid shows {len(rows)}")

    for item, row in zip(order.line_items, rows):
        problems.extend(comparisons.line_row_problems(item, row))

    return problems
