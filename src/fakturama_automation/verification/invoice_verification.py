from __future__ import annotations

from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import controls, readers, screens
from fakturama_automation.verification import comparisons, documents_list
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


def verify_invoice_saved(
    invoice_window: Any,
    normalized_order: NormalizedOrder,
    *,
    main_window: Any,
    order_window: Any,
    client: Any = None,
) -> bool:
    problems: list[str] = []

    title = readers.window_title(invoice_window)
    number = readers.document_number(title, unsaved_title=screens.INVOICE_TAB_TITLE_UNSAVED)
    if not number:
        problems.append(f"no invoice number assigned yet (editor still titled {title!r})")
    elif title.startswith(readers.UNSAVED_TAB_PREFIX):
        problems.append(f"invoice editor still has unsaved changes (titled {title!r})")

    cust_ref = readers.read_field_text(invoice_window, name=screens.INVOICE_CUST_REF_EDIT_NAME)
    if not comparisons.text_equals(normalized_order.external_reference, cust_ref):
        problems.append(f"Cust.Ref.: expected '{normalized_order.external_reference}', UI shows '{cust_ref}'")

    _, _, gross_total = comparisons.order_level_totals(normalized_order)
    total_text = readers.read_field_text(invoice_window, name=screens.INVOICE_TOTAL_EDIT_NAME)
    if not comparisons.money_equals(gross_total, total_text):
        problems.append(f"Total: expected {gross_total}, UI shows '{total_text}'")

    problems.extend(payment_problems(invoice_window, normalized_order))

    # Last, for the reason order_verification gives: reading Data > Documents
    # navigates away from this editor. Task 5.5 also wants the source Order
    # still open with the same Cust.Ref. and Total, so the Order's own tab
    # title supplies the second number to look up.
    order_title = readers.window_title(order_window)
    order_no = readers.document_number(order_title, unsaved_title=screens.ORDER_TAB_TITLE_UNSAVED)
    if not order_no:
        problems.append(f"source Order editor is no longer identifiable (titled {order_title!r})")
    elif number:
        try:
            problems.extend(
                documents_list.invoice_row_problems(
                    main_window,
                    normalized_order,
                    number=number,
                    order_number=order_no,
                    client=client,
                )
            )
        finally:
            controls.reactivate_editor(
                main_window,
                invoice_window,
                probe_type="Edit",
                probe_name=screens.INVOICE_CUST_REF_EDIT_NAME,
            )

    if problems:
        raise ManualReviewRequired(_SAVED_STEP, "; ".join(problems))
    return True

