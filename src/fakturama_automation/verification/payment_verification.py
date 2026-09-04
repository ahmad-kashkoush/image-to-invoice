"""Payment status fakturama_automation.verification.

Section 5 (verification).

TODO(section 5): re-read Invoice payment fields after applying payment
status via fakturama_automation.ui_automation. If status is PAID, also confirm payment date
and full invoice value were applied correctly, not just that the status
field shows PAID.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.normalization.models import NormalizedOrder


def verify_payment_applied(
    invoice_window: Any,
    normalized_order: NormalizedOrder,
) -> bool:
    """Confirm payment status (and, if PAID, payment date and full value)
    were applied correctly to the Invoice.

    TODO(section 5): implement. Should return False (or raise, routing to
    error_handling) on any mismatch.
    """
    raise NotImplementedError
