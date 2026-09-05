"""VAT rate resolution: search Fakturama by exact percent, create a new
VAT rate only if no exact match exists.

Section 4 (entity_resolution). Used when resolving a product that needs a
VAT rate not yet present in Fakturama (see product.py::_create_product).

Control identifiers below are pinned from probes/probe-08-vats.txt (list
view) and probes/probe-0801-vats.txt (create form), both re-probed on the
Windows 11 ARM VM with the VATs list/create form actually open - see
entity_resolution/config.py for the full selector inventory and its
provenance. Fakturama's own create form calls this entity "TAX Rate" (its
`Button`'s title is "Create a new tax rate", not "...VAT..."), even though
every other screen (nav label, list pane) says "VATs".

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
    `client` is the injectable vision client threaded through to
    resolver.search_grid_exact for reading the (UIA-invisible) VATs
    results grid. `settle_seconds` overrides search_grid_exact's fixed
    settle delay (tests pass 0).
    """
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_vats_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            search_edit_auto_id=config.VAT_SEARCH_EDIT_AUTO_ID,
            grid_pane_auto_id=config.VAT_LIST_PANE_AUTO_ID,
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
    click_input() pattern as debtor._open_debtors_list; see its
    docstring).
    """
    controls.find_control(main_window, "Text", name="VATs").click_input()


def _create_vat_rate(main_window: Any, vat_percent: Decimal) -> Any:
    """Open the New TAX Rate form, fill its Name and Value fields, save.

    Only Name and Value are filled - the form's Category, Description, and
    "VAT code (E-Invoice)" fields (probes/probe-0801-vats.txt) are
    optional and left at their defaults, the same "fill what's needed"
    approach as debtor._create_debtor/product._create_product.
    """
    controls.find_control(main_window, "Button", name=config.VAT_NEW_BUTTON_TITLE).click_input()

    name_edit = controls.find_control(main_window, "Edit", auto_id=config.VAT_FORM_NAME_AUTO_ID)
    name_edit.set_text(f"{vat_percent}%")

    controls.find_control(main_window, "Edit", auto_id=config.VAT_FORM_PERCENT_AUTO_ID).set_text(str(vat_percent))

    controls.find_control(main_window, "Button", name=config.SAVE_BUTTON_TITLE).click_input()
    return name_edit
