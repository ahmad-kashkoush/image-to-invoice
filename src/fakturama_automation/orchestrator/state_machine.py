"""The one verify-before-advance state machine.

States, in order:
1.  EXTRACT: read the order image (vision LLM, with an OCR fallback pass).
2.  NORMALIZE: convert and validate. Everything after this works from a
    record whose required fields, line totals and confidences are already
    established, so no later state re-runs those checks.
3.  OPEN_ORDER: open a new Order in Fakturama.
4.  POPULATE_ORDER_FIELDS: order-level fields, resolving Debtor and Payment
    Method.
5.  ADD_ORDER_LINES: one line at a time, resolving each Product by exact
    SKU. Each line is read back and compared column by column immediately
    after entry (inside the step) - a write to that grid is a click at a
    computed coordinate and can miss silently, so the check belongs on the
    line just entered, not at the end.
6.  VALIDATE_ORDER: read the Order's own totals back and compare them
    before saving (Task 4.1/4.3). The first check that can catch a
    whole-order problem the per-line checks cannot see.
7.  SAVE_AND_VERIFY_ORDER: save, then confirm it persisted.
8.  CREATE_AND_VERIFY_INVOICE: create the linked Invoice, verify it against
    the same record.
9.  APPLY_AND_VERIFY_PAYMENT: apply payment method (and date/value if
    paid), then verify.
10. SAVE_AND_VERIFY_INVOICE: save the Invoice and confirm it persisted with
    its payment data. Its own state for the same reason as 7: everything
    before it only proves what an open editor holds, and an editor is not
    the database.

Every state either advances or raises. run_workflow catches
ManualReviewRequired - and every mechanical ui_automation failure,
converting it into one named for the state that was running - and routes it
to the manual review queue, the single stop point for a run.
"""

from __future__ import annotations

import enum
import logging
from pathlib import Path
from typing import Any

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.error_handling.manual_review import route_to_manual_review
from fakturama_automation.extraction import extract_order
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.normalization.normalizer import normalize_order
from fakturama_automation.orchestrator import config, steps
from fakturama_automation.ui_automation import screens
from fakturama_automation.ui_automation.exceptions import (
    AmbiguousControlError,
    ControlNotFoundError,
    DialogTimeoutError,
    GridGeometryError,
    GridReadError,
    WindowFocusError,
)
from fakturama_automation.verification.invoice_verification import (
    verify_invoice_matches_order,
    verify_invoice_saved,
)
from fakturama_automation.verification.order_verification import (
    verify_order_before_save,
    verify_order_saved,
)
from fakturama_automation.verification.payment_verification import verify_payment_applied


class WorkflowState(enum.Enum):
    """States of the order-to-invoice workflow, in execution order."""

    # These two carry the step names extraction/normalization raise with, so
    # a queue entry and the CLI's own "stopped at" line always agree. Every
    # other value already matches the step its module raises under.
    EXTRACT = "extraction"
    NORMALIZE = "normalization"
    OPEN_ORDER = "open_order"
    POPULATE_ORDER_FIELDS = "populate_order_fields"
    ADD_ORDER_LINES = "add_order_lines"
    VALIDATE_ORDER = "validate_order"
    SAVE_AND_VERIFY_ORDER = "save_and_verify_order"
    CREATE_AND_VERIFY_INVOICE = "create_and_verify_invoice"
    APPLY_AND_VERIFY_PAYMENT = "apply_and_verify_payment"
    SAVE_AND_VERIFY_INVOICE = "save_and_verify_invoice"
    DONE = "done"


logger = logging.getLogger(__name__)


def _enter(state: WorkflowState) -> WorkflowState:
    """Record the state being entered and return it, so the loop below reads
    as a sequence of states rather than a sequence of assignments plus log
    calls. A run drives a desktop app for minutes; without this it produces
    no output at all until it is over.
    """
    logger.info("%s", state.value)
    return state


def extract_and_normalize(image_path: Path, *, client: Any = None) -> NormalizedOrder:
    """The two states that need no Fakturama window: EXTRACT, then
    NORMALIZE.

    Raises ManualReviewRequired rather than routing it - the caller decides
    what to do, which is what lets the CLI offer a --dry-run that reports a
    normalization failure without touching the UI.
    """
    _enter(WorkflowState.EXTRACT)
    raw_order = extract_order(image_path, client=client)
    _enter(WorkflowState.NORMALIZE)
    return normalize_order(raw_order)


# Every mechanical failure ui_automation can raise. None of them decides on
# its own that a human must look at the order - only this module knows which
# step was running (Doc/adr/0007 Decision 3).
_UI_DISCOVERY_ERRORS = (
    ControlNotFoundError,
    AmbiguousControlError,
    DialogTimeoutError,
    WindowFocusError,
    GridReadError,
    GridGeometryError,
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

    `app` defaults to a FakturamaApp connected to the running window;
    passing a duck-typed fake is the seam that avoids a real one. `client`
    is the injectable vision client, threaded through extraction, entity
    resolution and verification alike - one client for the whole run.

    Returns the last state reached: DONE on success, otherwise the state
    that stopped. A ManualReviewRequired never escapes (it goes to the
    queue), so this return value is the only way a caller can tell the two
    apart - __main__ turns it into the process exit code.
    """
    state = _enter(WorkflowState.EXTRACT)
    try:
        raw_order = extract_order(image_path, client=client)

        state = _enter(WorkflowState.NORMALIZE)
        order = normalize_order(raw_order)

        if app is None:
            # Deferred: ui_automation.app imports pywinauto.Application,
            # which fails off Windows - keeps this module importable
            # cross-platform for callers that pass a fake `app`.
            from fakturama_automation.ui_automation.app import FakturamaApp

            app = FakturamaApp()
            app.connect(screens.APP_TITLE_RE)

        state = _enter(WorkflowState.OPEN_ORDER)
        window = steps.open_new_order(app)

        state = _enter(WorkflowState.POPULATE_ORDER_FIELDS)
        steps.populate_order_fields(app, window, order, client=client, settle_seconds=settle_seconds)

        state = _enter(WorkflowState.ADD_ORDER_LINES)
        for index, item in enumerate(order.line_items):
            steps.add_order_line(
                app, window, item, position=index + 1, client=client, settle_seconds=settle_seconds
            )

        state = _enter(WorkflowState.VALIDATE_ORDER)
        verify_order_before_save(window, order)

        state = _enter(WorkflowState.SAVE_AND_VERIFY_ORDER)
        steps.save_order(app, window)
        verify_order_saved(window, order, client=client)

        state = _enter(WorkflowState.CREATE_AND_VERIFY_INVOICE)
        invoice_window = steps.create_linked_invoice(app, window, client=client)
        verify_invoice_matches_order(invoice_window, order, client=client)

        state = _enter(WorkflowState.APPLY_AND_VERIFY_PAYMENT)
        steps.apply_payment(app, invoice_window, order, client=client)
        verify_payment_applied(invoice_window, order, client=client)

        state = _enter(WorkflowState.SAVE_AND_VERIFY_INVOICE)
        steps.save_invoice(app, invoice_window)
        verify_invoice_saved(invoice_window, order, client=client)

        logger.info("%s", WorkflowState.DONE.value)
        return WorkflowState.DONE
    except ManualReviewRequired as error:
        logger.warning("stopped at %s: %s", error.step, error.reason)
        route_to_manual_review(error, str(image_path), out_dir=out_dir)
        return state
    except _UI_DISCOVERY_ERRORS as error:
        logger.warning("stopped at %s: %s", state.value, error)
        route_to_manual_review(ManualReviewRequired(state.value, str(error)), str(image_path), out_dir=out_dir)
        return state
