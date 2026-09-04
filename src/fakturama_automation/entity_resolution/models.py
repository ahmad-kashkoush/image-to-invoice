"""Result type returned by every entity resolver.

Section 4 (entity_resolution). Not dictated by the original scaffold (which
typed every resolver's return as a bare Any) - see
Doc/adr/0003-entity-resolution.md for why a named result type was
introduced instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ResolvedEntity:
    """What a resolver found or created, and what later steps need from it.

    identity: the exact key that was matched or just created (company
    name, SKU, VAT percent as text, payment method name) - useful for
    logging and for verification.py to confirm against, without needing to
    re-read the UI.
    created: True if no exact match existed and a new record was created,
    False if an existing record was matched. Verification and the
    manual-review log care about this distinction (a newly created Debtor
    is a bigger deal to get wrong than one already in Fakturama).
    element: whatever UI reference identifies this record to later
    ui_automation steps (e.g. the opened record's window/pane, read back
    after selection or creation). Left untyped (Any) - see ui_automation's
    own use of Any for pywinauto objects (Doc/adr/0002) - and optional
    since a pure/offline caller may not have one.
    """

    identity: str
    created: bool
    element: Any = None
