"""Product resolution: search Fakturama by exact SKU, create a new
Product only if no exact match exists.

Control identifiers are pinned from live VM probes and live in
ui_automation/screens.py, the one selector inventory for every screen.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.entity_resolution import combos, config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.entity_resolution.vat_rate import resolve_vat_rate
from fakturama_automation.normalization.models import NormalizedLineItem
from fakturama_automation.normalization.validators import gross_from_net
from fakturama_automation.ui_automation import controls, locators, screens


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
    `client` is the injectable vision client for reading the Products
    results grid.

    A missing VAT rate for a new product is created via
    vat_rate.resolve_vat_rate *before* the product form is filled in, so
    the product's VAT combo always has an option to select.
    """
    sku = item.sku
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_products_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            grid_pane_name=screens.PRODUCTS_GRID_PANE_NAME,
            key=sku,
            columns=screens.PRODUCTS_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, sku, read=lambda row: row[screens.PRODUCTS_SEARCH_COLUMNS[0]])
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
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.PRODUCTS_NAV_NAME).click_input()


def _create_product(main_window: Any, item: NormalizedLineItem, *, client: Any = None) -> Any:
    """Open the New Product form, fill it from the normalized line item,
    select its VAT rate, and save. Returns the SKU edit control as the
    resolved record's `element` (the editor tab/pane's own title and
    auto_id are unstable once data is entered).

    `client` is the injectable vision client for reading the VAT combo's
    real options.

    Item Number, Name, and the VAT combo are selected by accessible NAME,
    not auto_id (auto_ids are session-unstable). Price (gross) is
    blank-named, so it's located structurally instead - the Edit inside
    the Pane immediately following the "Price (gross)" Text in their
    shared parent, the same sibling-Pane pattern debtor.py uses.

    That price field is GROSS, and the line item's price is net, so the
    value typed is converted first (validators.gross_from_net). Writing the
    net figure straight in - the previous behavior - made Fakturama derive
    a net price of net / (1 + VAT) for every Order line built from this
    record: confirmed live, a 250.00 net chair became $210.08 a unit and
    $378.15 for two, with nothing raising an error until final
    verification.

    Every field is filled via controls.type_text (real keystrokes), not
    set_text(): set_text() can silently fail to persist a freshly-created
    record's field through Save with no reliable rule for which field is
    affected, so keystrokes are used uniformly here.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.PRODUCT_NEW_BUTTON_TITLE).click_input()

    sku_edit = controls.find_control(main_window, "Edit", name=screens.PRODUCT_SKU_EDIT_NAME)
    controls.type_text(sku_edit, item.sku)

    if item.description:
        controls.type_text(controls.find_control(main_window, "Edit", name=screens.PRODUCT_NAME_EDIT_NAME), item.description)

    if item.unit_net_price:
        price_pane = locators.sibling_pane_after_label(
            main_window, screens.PRODUCT_PRICE_GROSS_LABEL_NAME
        )
        price_edit = price_pane.descendants(control_type="Edit")[0]
        controls.type_text(price_edit, str(gross_from_net(item.unit_net_price, item.vat_percent)))

    # Selected by reading the combo's real, currently-open options and
    # clicking the matching one (combos.select_vat_option) - never a
    # guessed option string - so an unexpected VAT option format fails
    # closed to manual review instead of raising a raw pywinauto error.
    vat_combo = controls.find_control(main_window, "ComboBox", name=screens.PRODUCT_VAT_COMBO_NAME)
    combos.select_vat_option(main_window, vat_combo, item.vat_percent, client=client, step="resolve_product")

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()
    return sku_edit
