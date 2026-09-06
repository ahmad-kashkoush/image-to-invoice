"""The one verify before advance state machine.

States, in order:
1. EXTRACT: read the order image via extraction.extract_order (vision LLM
   first, with an OCR fallback pass for low confidence fields).
2. NORMALIZE: convert and validate via normalization.normalize_order, stop
   here on any failed check.
3. OPEN_ORDER: open a new Order in Fakturama via orchestrator.actions.
4. POPULATE_ORDER_FIELDS: fill order level fields, resolving Debtor and
   Payment Method via entity_resolution.debtor / entity_resolution.
   payment_method.
5. ADD_ORDER_LINES: add lines one at a time, resolving each Product by
   exact SKU via entity_resolution.product, creating its VAT rate via
   entity_resolution.vat_rate if needed, and checking each line's
   calculated total against the source total immediately after entry.
6. VALIDATE_ORDER: validate addresses, products, and the overall total
   before saving.
7. SAVE_AND_VERIFY_ORDER: save the Order and verify via
   verification.order_verification.
8. CREATE_AND_VERIFY_INVOICE: create the linked Invoice from the saved
   Order and verify via verification.invoice_verification.
9. APPLY_AND_VERIFY_PAYMENT: apply payment method (and, if status is
   PAID, payment date and full invoice value), then verify via
   verification.payment_verification.

Every state either advances or raises ManualReviewRequired; run_workflow
catches it (and any control-discovery failure from ui_automation, converted
into one) at the top level and routes it to error_handling.manual_review -
the single stop point for this whole run. `state` tracks the last state
reached so a converted control-discovery failure is reported against the
right step.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any

from fakturama_automation.entity_resolution.config import APP_TITLE_RE
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.error_handling.manual_review import route_to_manual_review
from fakturama_automation.extraction import extract_order
from fakturama_automation.normalization.config import DEFAULT_LINE_TOTAL_TOLERANCE
from fakturama_automation.normalization.normalizer import normalize_order
from fakturama_automation.normalization.validators import check_line_total, check_required_fields
from fakturama_automation.orchestrator import actions, config
from fakturama_automation.ui_automation.exceptions import (
    AmbiguousControlError,
    ControlNotFoundError,
    DialogTimeoutError,
    WindowFocusError,
)
from fakturama_automation.verification.invoice_verification import verify_invoice_matches_order
from fakturama_automation.verification.order_verification import verify_order_saved
from fakturama_automation.verification.payment_verification import verify_payment_applied


class WorkflowState(enum.Enum):
    """States of the order-to-invoice workflow, in execution order."""

    EXTRACT = "extract"
    NORMALIZE = "normalize"
    OPEN_ORDER = "open_order"
    POPULATE_ORDER_FIELDS = "populate_order_fields"
    ADD_ORDER_LINES = "add_order_lines"
    VALIDATE_ORDER = "validate_order"
    SAVE_AND_VERIFY_ORDER = "save_and_verify_order"
    CREATE_AND_VERIFY_INVOICE = "create_and_verify_invoice"
    APPLY_AND_VERIFY_PAYMENT = "apply_and_verify_payment"
    DONE = "done"

_UI_DISCOVERY_ERRORS = (
    ControlNotFoundError,
    AmbiguousControlError,
    DialogTimeoutError,
    WindowFocusError,
)


def run_workflow(
    image_path: Path,
    *,
    app: Any = None,
    client: Any = None,
    out_dir: str | Path | None = None,
    settle_seconds: float = config.SETTLE_SECONDS,
) -> WorkflowState:
    """Run the full state machine for a single order image.

    `app` defaults to a FakturamaApp connected to the running Fakturama
    window; passing one in (a duck-typed fake) is the seam tests use to
    avoid a real window. `client` is the injectable vision client threaded
    through extraction, entity resolution, and verification alike - one
    client for the whole run. Returns the last state reached
    (WorkflowState.DONE on success).
    """
    state = WorkflowState.EXTRACT
    try:
        raw_order = extract_order(image_path, client=client)

        state = WorkflowState.NORMALIZE
        order = normalize_order(raw_order)

        if app is None:
            # Deferred import: ui_automation.app imports pywinauto.Application
            # directly, which fails off Windows - keeps this module
            # importable cross-platform for callers that pass a fake `app`.
            from fakturama_automation.ui_automation.app import FakturamaApp

            app = FakturamaApp()
            app.connect(APP_TITLE_RE)

        state = WorkflowState.OPEN_ORDER
        window = actions.open_new_order(app)

        state = WorkflowState.POPULATE_ORDER_FIELDS
        actions.populate_order_fields(app, window, order, client=client, settle_seconds=settle_seconds)

        state = WorkflowState.ADD_ORDER_LINES
        for index, item in enumerate(order.line_items):
            actions.add_order_line(
                app, window, item, position=index + 1, client=client, settle_seconds=settle_seconds
            )
            if not check_line_total(item, DEFAULT_LINE_TOTAL_TOLERANCE):
                raise ManualReviewRequired(
                    state.value,
                    f"line {index + 1} ({item.sku or '?'}): recomputed total {item.recomputed_total} "
                    f"does not match source total {item.source_line_total}",
                )

        state = WorkflowState.VALIDATE_ORDER
        if not check_required_fields(order):
            raise ManualReviewRequired(state.value, "order failed required-fields validation before save")

        state = WorkflowState.SAVE_AND_VERIFY_ORDER
        actions.save_order(app, window)
        verify_order_saved(window, order, client=client)

        state = WorkflowState.CREATE_AND_VERIFY_INVOICE
        invoice_window = actions.create_linked_invoice(app, window, client=client)
        verify_invoice_matches_order(invoice_window, order, client=client)

        state = WorkflowState.APPLY_AND_VERIFY_PAYMENT
        actions.apply_payment(app, invoice_window, order, client=client)
        verify_payment_applied(invoice_window, order, client=client)

        return WorkflowState.DONE
    except ManualReviewRequired as error:
        route_to_manual_review(error, str(image_path), out_dir=out_dir)
        return state
    except _UI_DISCOVERY_ERRORS as error:
        route_to_manual_review(ManualReviewRequired(state.value, str(error)), str(image_path), out_dir=out_dir)
        return state
