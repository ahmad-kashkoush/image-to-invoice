"""VAT rate resolution: search Fakturama by exact percent, create a new
VAT rate only if no exact match exists.

Section 4 (entity_resolution).

TODO(section 4): implement using resolver.resolve_exact_or_create(). Used
when resolving a product that needs a VAT rate not yet present in
Fakturama.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def resolve_vat_rate(vat_percent: Decimal) -> Any:
    """Resolve a VAT percent to a Fakturama VAT rate record, by exact
    percent match.

    TODO(section 4): implement. Return type should be whatever identifies
    a Fakturama VAT rate to later ui_automation steps.
    """
    raise NotImplementedError
