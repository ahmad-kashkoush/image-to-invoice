"""Payment method resolution: search Fakturama by exact name, create a new
payment method only if no exact match exists.

Section 4 (entity_resolution). Fakturama calls this entity "terms of
payment" in its own UI (see the left Navigation View label). The search
half is fully probed (probes/probe-09-Payment.txt) and implemented below;
the create half is not - that probe captured the "Create a new term of
payment" button but not the form it opens (a stale Product editor was
still open when the probe ran), so its field auto_ids are unknown. Calling
create() (resolving a payment method Fakturama doesn't already have)
raises a clear RuntimeError naming the gap, rather than guessing field
names or silently doing nothing. See .claude/plans/entity-resolution.md's
"Remaining probe gap" for exactly what to re-probe; once
entity_resolution/config.py's PAYMENT_FORM_NAME_AUTO_ID is filled in, this
should follow the same _create_* shape as debtor.py/product.py.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.entity_resolution import config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.ui_automation import controls

_SEARCH_COLUMNS = ["Name"]


def resolve_payment_method(
    app: Any,
    payment_method: str,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    """Resolve a payment method name to a Fakturama record, by exact
    name match.

    `app` is a connected FakturamaApp-like handle (`.main_window()` only).
    `client` is the injectable vision client threaded through to
    resolver.search_grid_exact for reading the (UIA-invisible) payment
    methods results grid. `settle_seconds` overrides search_grid_exact's
    fixed settle delay (tests pass 0).
    """
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_payment_methods_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            search_edit_auto_id=config.PAYMENT_SEARCH_EDIT_AUTO_ID,
            grid_pane_auto_id=config.PAYMENT_LIST_PANE_AUTO_ID,
            key=payment_method,
            columns=_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, payment_method, read=lambda row: row["Name"])
        return [ResolvedEntity(identity=payment_method, created=False, element=row) for row in matches]

    def create() -> ResolvedEntity:
        raise RuntimeError(
            f"cannot create payment method {payment_method!r}: the 'Create a new term of "
            "payment' form has not been probed yet (entity_resolution.config."
            "PAYMENT_FORM_NAME_AUTO_ID is None) - see .claude/plans/entity-resolution.md's "
            "'Remaining probe gap'"
        )

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"payment method '{payment_method}'", step="resolve_payment_method"
    )


def _open_payment_methods_list(main_window: Any) -> None:
    """Select the "terms of payment" list from the left Navigation View
    (same click_input() pattern as debtor._open_debtors_list; see its
    docstring). Fakturama's own nav label is "terms of payment", not
    "Payment methods" - confirmed in probes/probe-00-root.txt.
    """
    controls.find_control(main_window, "Text", name="terms of payment").click_input()
