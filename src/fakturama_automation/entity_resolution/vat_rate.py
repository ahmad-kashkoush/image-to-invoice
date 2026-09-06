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
from fakturama_automation.ui_automation import controls, screens

# read_grid_rows column labels for the vision pass - the results grid's
# rows are UIA-invisible (like every other entity's), so these aren't
# independently confirmed from the probe; they mirror the create form's
# own "Name"/"Value" field labels (entity_resolution/config.py).


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
            grid_pane_name=screens.VATS_GRID_PANE_NAME,
            key=str(vat_percent),
            columns=screens.VATS_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_vat_matches(rows, vat_percent, read=lambda row: row[screens.VATS_SEARCH_COLUMNS[1]])
        return [ResolvedEntity(identity=f"{vat_percent}%", created=False) for _ in matches]

    def create() -> ResolvedEntity:
        _create_vat_rate(main_window, vat_percent, settle_seconds=settle_seconds)
        return ResolvedEntity(identity=f"{vat_percent}%", created=True)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"VAT rate {vat_percent}%", step="resolve_vat_rate"
    )


def _open_vats_list(main_window: Any) -> None:
    """Select the VATs list from the left Navigation View (same
    click_input() pattern as debtor._open_debtors_list).
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.VATS_NAV_NAME).click_input()


def _create_vat_rate(
    main_window: Any,
    vat_percent: Decimal,
    *,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    """Open the New TAX Rate form, fill Name and Value, save, and
    confirm the save took.

    Only Name and Value are filled - Category/Description/"VAT code
    (E-Invoice)" are optional and left at their defaults.

    Value is written with controls.replace_text, not type_text: it comes
    pre-filled with "0%", and plain type_text (click + type, no clear)
    inserts into that existing "0%" instead of replacing it, so Fakturama
    silently saved the record with Value "0%" regardless of what was typed.
    Every other field in this module starts out blank.

    This is the record whose silent mis-save started the worst bug in this
    project's history, which is why the read-back below checks Value
    numerically as well as Name: a rate saved as 0% is invisible to this
    resolver's own next search, so every run created another duplicate.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.VAT_NEW_BUTTON_TITLE).click_input()

    controls.find_control(main_window, "Edit", name=screens.VAT_NAME_EDIT_NAME).set_text(f"{vat_percent}%")

    value_edit = controls.find_control(main_window, "Edit", name=screens.VAT_VALUE_EDIT_NAME)
    controls.replace_text(value_edit, str(vat_percent))

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()

    resolver.verify_saved_fields(
        main_window,
        [
            (screens.VAT_NAME_EDIT_NAME, f"{vat_percent}%", resolver.text_matches),
            (screens.VAT_VALUE_EDIT_NAME, str(vat_percent), resolver.percent_matches),
        ],
        entity=f"VAT rate {vat_percent}%",
        step="resolve_vat_rate",
        settle_seconds=settle_seconds,
    )
