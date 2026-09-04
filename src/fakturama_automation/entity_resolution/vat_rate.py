"""VAT rate resolution: search Fakturama by exact percent, create a new
VAT rate only if no exact match exists.

Section 4 (entity_resolution). Used when resolving a product that needs a
VAT rate not yet present in Fakturama (see product.py::_create_product).

BLOCKED on a probe gap, unlike debtor.py/product.py/payment_method.py:
probes/probe-08-vats.txt captured a stale Product editor instead of the
VATs list or its create form (the VATs list pane never rendered in that
capture), so - unlike Debtor/Product/Payment - there is no known auto_id
yet for the VAT search box, results pane, "New" button, or create-form
fields (name, percent value). See .claude/plans/entity-resolution.md's
"Remaining probe gap" for exactly what to re-probe: open the VATs list
from the left Navigation View, and its "New VAT" form, with no other
editor left open first.

Once entity_resolution/config.py's VAT_* constants are filled in from that
re-probe, this should follow the exact same shape as
payment_method.py/debtor.py: resolver.search_grid_exact for the search
half (matching.exact_vat_matches, not exact_text_matches, since the match
is numeric), a small _create_vat_rate for the create half.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def resolve_vat_rate(app: Any, vat_percent: Decimal, *, client: Any = None) -> Any:
    """Resolve a VAT percent to a Fakturama VAT rate record, by exact
    percent match.

    Not yet implemented - see module docstring for exactly what's
    blocking it (a probe gap, not a design gap).
    """
    raise NotImplementedError(
        "resolve_vat_rate needs the VATs list/create-form probe - see this module's docstring "
        "and .claude/plans/entity-resolution.md's 'Remaining probe gap'"
    )
