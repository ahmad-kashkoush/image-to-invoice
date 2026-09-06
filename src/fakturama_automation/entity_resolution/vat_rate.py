"""VAT rate resolution: search Fakturama by exact percent, create a new
VAT rate only if no exact match exists.

Used when resolving a product that needs a VAT rate not yet present in
Fakturama (see product.py::_create_product). Fakturama's own create form
calls this entity "TAX Rate", even though every other screen says "VATs".

Follows the same search_grid_exact + resolve_exact_or_create shape as
debtor.py/product.py, but matches numerically (matching.exact_vat_matches),
not by exact text, since the search key is a VAT percent rather than a
name.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fakturama_automation.entity_resolution import config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.ui_automation import controls

# read_grid_rows column labels for the vision pass - the results grid's
# rows are UIA-invisible (like every other entity's), so these aren't
# independently confirmed from the probe; they mirror the create form's
# own "Name"/"Value" field labels (entity_resolution/config.py).
_SEARCH_COLUMNS = ["Name", "Value"]


def resolve_vat_rate(
    app: Any,
    vat_percent: Decimal,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    """Resolve a VAT percent to a Fakturama VAT rate record, by exact
    percent match.

    `app` is a connected FakturamaApp-like handle (`.main_window()` only).
    `client` is the injectable vision client for reading the VATs results
    grid.
    """
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_vats_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            grid_pane_name="VATs",
            key=str(vat_percent),
            columns=_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_vat_matches(rows, vat_percent, read=lambda row: row["Value"])
        return [ResolvedEntity(identity=f"{vat_percent}%", created=False, element=row) for row in matches]

    def create() -> ResolvedEntity:
        element = _create_vat_rate(main_window, vat_percent)
        return ResolvedEntity(identity=f"{vat_percent}%", created=True, element=element)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"VAT rate {vat_percent}%", step="resolve_vat_rate"
    )


def _open_vats_list(main_window: Any) -> None:
    """Select the VATs list from the left Navigation View (same
    click_input() pattern as debtor._open_debtors_list).
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name="VATs").click_input()


def _create_vat_rate(main_window: Any, vat_percent: Decimal) -> Any:
    """Open the New TAX Rate form, fill its Name and Value fields, save.

    Only Name and Value are filled - Category/Description/"VAT code
    (E-Invoice)" are optional and left at their defaults.

    Selected by accessible NAME ("Name"/"Value"), not auto_id - neither
    Edit is actually blank-named.

    Value's default content ("0%") is cleared before typing, then committed
    with a trailing Tab: confirmed live that plain controls.type_text
    (click + type, no clear) inserts into that existing "0%" instead of
    replacing it, so Fakturama silently saves the record with Value "0%"
    regardless of what was typed - real keystrokes alone (without the
    clear+Tab) aren't enough here, unlike every other field in this module
    that starts out blank.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=config.VAT_NEW_BUTTON_TITLE).click_input()

    name_edit = controls.find_control(main_window, "Edit", name="Name")
    name_edit.set_text(f"{vat_percent}%")

    value_edit = controls.find_control(main_window, "Edit", name="Value")
    value_edit.click_input()
    value_edit.type_keys("^a{DELETE}")
    value_edit.type_keys(controls.escape_send_keys(str(vat_percent)), with_spaces=True)
    value_edit.type_keys("{TAB}")

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=config.SAVE_BUTTON_TITLE).click_input()
    return name_edit
