"""Payment method resolution: search Fakturama by exact name, create a new
payment method only if no exact match exists.

Fakturama calls this entity "terms of payment" in its own UI, but "New
Term of Payment" in the create form's own tab title.
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
    `client` is the injectable vision client for reading the payment
    methods results grid.
    """
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_payment_methods_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            grid_pane_name="terms of payment",
            key=payment_method,
            columns=_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, payment_method, read=lambda row: row["Name"])
        return [ResolvedEntity(identity=payment_method, created=False, element=row) for row in matches]

    def create() -> ResolvedEntity:
        element = _create_payment_method(main_window, payment_method)
        return ResolvedEntity(identity=payment_method, created=True, element=element)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"payment method '{payment_method}'", step="resolve_payment_method"
    )


def _open_payment_methods_list(main_window: Any) -> None:
    """Select the "terms of payment" list from the left Navigation View
    (same click_input() pattern as debtor._open_debtors_list). Fakturama's
    own nav label is "terms of payment", not "Payment methods".
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name="terms of payment").click_input()


def _create_payment_method(main_window: Any, payment_method: str) -> Any:
    """Open the New Term of Payment form, fill its Name field, save.

    Only Name is filled - Account/Description/Payment code/Cash discount/
    Discount Days/Net Days are all optional and left at their defaults.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=config.PAYMENT_NEW_BUTTON_TITLE).click_input()

    name_edit = controls.find_control(main_window, "Edit", name="Name")
    name_edit.set_text(payment_method)

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=config.SAVE_BUTTON_TITLE).click_input()
    return name_edit
