"""Payment method resolution: search Fakturama by exact name, create a new
payment method only if no exact match exists.

Section 4 (entity_resolution).

TODO(section 4): implement using resolver.resolve_exact_or_create().
"""

from __future__ import annotations

from typing import Any


def resolve_payment_method(payment_method: str) -> Any:
    """Resolve a payment method name to a Fakturama record, by exact
    name match.

    TODO(section 4): implement. Return type should be whatever identifies
    a Fakturama payment method to later ui_automation steps.
    """
    raise NotImplementedError
