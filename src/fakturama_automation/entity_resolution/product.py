"""Product resolution: search Fakturama by exact SKU, create a new
Product only if no exact match exists.

Section 4 (entity_resolution) and orchestrator's per-line resolution step.

TODO(section 4): implement using resolver.resolve_exact_or_create(),
searching Fakturama's product list via ui_automation by SKU. A missing
VAT rate for a new product should be created via vat_rate.py, not
skipped.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.normalization.models import NormalizedLineItem


def resolve_product(item: NormalizedLineItem) -> Any:
    """Resolve a line item's product for a normalized order to a
    Fakturama record, by exact SKU.

    TODO(section 4): implement. Return type should be whatever identifies
    a Fakturama Product to later ui_automation steps.
    """
    raise NotImplementedError
