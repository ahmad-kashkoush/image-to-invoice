"""Debtor resolution: search Fakturama by exact company name (and alias if
present), create a new Debtor only if no exact match exists.

Section 4 (entity_resolution).

TODO(section 4): implement using resolver.resolve_exact_or_create(),
searching Fakturama's contact/debtor list via ui_automation and filling
the new Debtor form via ui_automation when creation is needed.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.normalization.models import NormalizedOrder


def resolve_debtor(order: NormalizedOrder) -> Any:
    """Resolve the debtor for a normalized order to a Fakturama record.

    TODO(section 4): implement. Return type should be whatever identifies
    a Fakturama Debtor to later ui_automation steps (e.g. its UI reference
    or an internal id read back after selection/creation).
    """
    raise NotImplementedError
