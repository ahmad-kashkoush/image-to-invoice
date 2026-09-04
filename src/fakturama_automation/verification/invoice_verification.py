"""Invoice creation fakturama_automation.verification.

Section 5 (verification).

TODO(section 5): re-verify the created Invoice independently against the
normalized record, not just by trusting the create action succeeded. Read
the Invoice's fields back via ui_automation and compare against the
NormalizedOrder it was created from.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.normalization.models import NormalizedOrder


def verify_invoice_matches_order(
    invoice_window: Any,
    normalized_order: NormalizedOrder,
) -> bool:
    """Confirm the created Invoice's fields match normalized_order.

    TODO(section 5): implement. Should return False (or raise, routing to
    error_handling) on any mismatch.
    """
    raise NotImplementedError
