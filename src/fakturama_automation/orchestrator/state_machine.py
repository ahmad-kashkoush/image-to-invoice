"""The one verify before advance state machine.

TODO: implement each state below as a function or method that performs
its step, then verifies before returning control to run_workflow(). Any
failure should raise fakturama_automation.error_handling.exceptions.ManualReviewRequired
rather than let a bad state advance to the next one.

States, in order:
1. EXTRACT: read the order image via fakturama_automation.extraction.vision_extractor, fall
   back to fakturama_automation.extraction.ocr_fallback for low confidence fields.
2. NORMALIZE: convert and validate via fakturama_automation.normalization.normalizer, stop
   here on any failed check.
3. OPEN_ORDER: open a new Order in Fakturama via fakturama_automation.ui_automation.
4. POPULATE_ORDER_FIELDS: fill order level fields, resolving Debtor and
   Payment Method via fakturama_automation.entity_resolution.debtor / fakturama_automation.entity_resolution.
   payment_method.
5. ADD_ORDER_LINES: add lines one at a time, resolving each Product by
   exact SKU via fakturama_automation.entity_resolution.product, creating its VAT rate via
   fakturama_automation.entity_resolution.vat_rate if needed, and checking each line's
   calculated total against the source total immediately after entry.
6. VALIDATE_ORDER: validate addresses, products, and the overall total
   before saving.
7. SAVE_AND_VERIFY_ORDER: save the Order and verify via
   fakturama_automation.verification.order_verification.
8. CREATE_AND_VERIFY_INVOICE: create the linked Invoice from the saved
   Order and verify via fakturama_automation.verification.invoice_verification.
9. APPLY_AND_VERIFY_PAYMENT: apply payment method (and, if status is
   PAID, payment date and full invoice value), then verify via
   fakturama_automation.verification.payment_verification.
"""

from __future__ import annotations

import enum
from pathlib import Path


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


def run_workflow(image_path: Path) -> None:
    """Run the full state machine for a single order image.

    TODO: implement the state loop described in the module docstring,
    catching fakturama_automation.error_handling.exceptions.ManualReviewRequired at the top
    level and routing it to fakturama_automation.error_handling.manual_review.
    """
    raise NotImplementedError
