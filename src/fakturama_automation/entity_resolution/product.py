"""Product resolution: search Fakturama by exact SKU, create a new
Product only if no exact match exists.

Section 4 (entity_resolution) and orchestrator's per-line resolution step.
Control identifiers below are pinned from probes/probe-07-products.txt,
fully probed on the Windows 11 ARM VM - see entity_resolution/config.py
for the full selector inventory and its provenance.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.entity_resolution import combos, config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.entity_resolution.vat_rate import resolve_vat_rate
from fakturama_automation.normalization.models import NormalizedLineItem
from fakturama_automation.ui_automation import controls

_SEARCH_COLUMNS = ["Item Number"]


def resolve_product(
    app: Any,
    item: NormalizedLineItem,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    """Resolve a line item's product for a normalized order to a
    Fakturama record, by exact SKU.

    `app` is a connected FakturamaApp-like handle (`.main_window()` only).
    `client` is the injectable vision client threaded through to
    resolver.search_grid_exact for reading the (UIA-invisible) Products
    results grid. `settle_seconds` overrides search_grid_exact's fixed
    settle delay (tests pass 0).

    A missing VAT rate for a new product is created via
    vat_rate.resolve_vat_rate *before* the product form is filled in, so
    the product's VAT combo always has an option to select (never skipped
    - see product.py's original scaffold docstring).
    """
    sku = item.sku
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_products_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            search_edit_auto_id=config.PRODUCT_SEARCH_EDIT_AUTO_ID,
            grid_pane_auto_id=config.PRODUCT_LIST_PANE_AUTO_ID,
            key=sku,
            columns=_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, sku, read=lambda row: row["Item Number"])
        return [ResolvedEntity(identity=sku, created=False, element=row) for row in matches]

    def create() -> ResolvedEntity:
        resolve_vat_rate(app, item.vat_percent, client=client)
        element = _create_product(main_window, item, client=client)
        return ResolvedEntity(identity=sku, created=True, element=element)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"product SKU '{sku}'", step="resolve_product"
    )


def _open_products_list(main_window: Any) -> None:
    """Select the Products list from the left Navigation View (same
    click_input() pattern as debtor._open_debtors_list; see its docstring).
    """
    controls.find_control(main_window, "Text", name="Products").click_input()


def _create_product(main_window: Any, item: NormalizedLineItem, *, client: Any = None) -> Any:
    """Open the New Product form, fill it from the normalized line item,
    select its VAT rate, and save. Returns the SKU edit control as the
    resolved record's `element` (the editor tab/pane's own title and
    auto_id are unstable once data is entered - see debtor._create_debtor).

    `client` is the injectable vision client threaded through to
    combos.select_vat_option, which needs it to read the VAT combo's real
    options (see combos.py's docstring).
    """
    controls.find_control(main_window, "Button", name=config.PRODUCT_NEW_BUTTON_TITLE).click_input()

    sku_edit = controls.find_control(main_window, "Edit", auto_id=config.PRODUCT_FORM_SKU_AUTO_ID)
    sku_edit.set_text(item.sku)

    if item.description:
        controls.find_control(main_window, "Edit", auto_id=config.PRODUCT_FORM_NAME_AUTO_ID).set_text(
            item.description
        )

    if item.unit_net_price:
        controls.find_control(main_window, "Edit", auto_id=config.PRODUCT_FORM_PRICE_AUTO_ID).set_text(
            str(item.unit_net_price)
        )

    # Selected by reading the combo's real, currently-open options and
    # clicking the matching one (combos.select_vat_option) - never a
    # guessed option string - so an unexpected VAT option format fails
    # closed to manual review instead of raising a raw pywinauto error.
    vat_combo = controls.find_control(main_window, "ComboBox", auto_id=config.PRODUCT_FORM_VAT_COMBO_AUTO_ID)
    combos.select_vat_option(main_window, vat_combo, item.vat_percent, client=client, step="resolve_product")

    controls.find_control(main_window, "Button", name=config.SAVE_BUTTON_TITLE).click_input()
    return sku_edit
