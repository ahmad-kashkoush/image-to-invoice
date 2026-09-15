from __future__ import annotations

from decimal import Decimal
from typing import Any

from fakturama_automation.entity_resolution import combos, config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.entity_resolution.vat_rate import resolve_vat_rate
from fakturama_automation.normalization import parsing
from fakturama_automation.normalization.models import NormalizedLineItem
from fakturama_automation.normalization.validators import gross_from_net
from fakturama_automation.ui_automation import config as ui_config
from fakturama_automation.ui_automation import controls, locators, readers, screens


def resolve_product(
    app: Any,
    item: NormalizedLineItem,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
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
        return [ResolvedEntity(identity=sku, created=False) for _ in matches]

    def create() -> ResolvedEntity:
        # Before the form is filled, so its VAT combo always has an option.
        resolve_vat_rate(app, item.vat_percent, client=client)
        _create_product(main_window, item, client=client, settle_seconds=settle_seconds)
        return ResolvedEntity(identity=sku, created=True)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"product SKU '{sku}'", step="resolve_product"
    )


def _open_products_list(main_window: Any) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.PRODUCTS_NAV_NAME).click_input()


def _price_text(gross_price: Decimal) -> str:
    return parsing.format_decimal(gross_price, decimal_separator=ui_config.DECIMAL_SEPARATOR)


def _read_price_text(main_window: Any) -> str:
    # The Price (gross) Edit has no accessible name and its auto_id is
    # session-unstable, so it is reached the same way it is written: the
    # "Price (gross)" label's sibling pane, first Edit.
    price_pane = locators.sibling_pane_after_label(
        main_window, screens.PRODUCT_PRICE_GROSS_LABEL_NAME
    )
    return readers.field_value(price_pane.descendants(control_type="Edit")[0])


def _create_product(
    main_window: Any,
    item: NormalizedLineItem,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    # The price field is GROSS while the line item's price is net, so the value
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.PRODUCT_NEW_BUTTON_TITLE).click_input()

    controls.type_text(
        controls.find_control(main_window, "Edit", name=screens.PRODUCT_SKU_EDIT_NAME), item.sku
    )

    if item.description:
        controls.type_text(controls.find_control(main_window, "Edit", name=screens.PRODUCT_NAME_EDIT_NAME), item.description)

    gross_price = gross_from_net(item.unit_net_price, item.vat_percent)
    if item.unit_net_price:
        price_pane = locators.sibling_pane_after_label(
            main_window, screens.PRODUCT_PRICE_GROSS_LABEL_NAME
        )
        price_edit = price_pane.descendants(control_type="Edit")[0]
        # Two separate bugs have lived in this one line, both silent, both
        # found live:
        #  - replace_text, not type_text: the field is pre-filled with a
        #    formatted 0.00 and type_text inserts at the caret, so (2026-09-14)
        #    "297.50" became "297.500,00" = 297500.00, 1000x too high.
        #  - format_decimal, not str(): Fakturama parses this field in its own
        #    locale, where "." groups thousands, so (2026-09-15) the cleared
        #    field still took "297.50" as 29.750,00 EUR, 100x too high.
        # The read-back below is what stops a third one being silent too.
        controls.replace_text(price_edit, _price_text(gross_price))

    # Selected through UIA by exact option name, then read back and compared
    # numerically (combos.select_vat_option) - so an unexpected VAT option
    # format fails closed to manual review instead of raising a raw pywinauto
    # error or silently selecting a neighbouring rate.
    vat_combo = controls.find_control(main_window, "ComboBox", name=screens.PRODUCT_VAT_COMBO_NAME)
    combos.select_vat_option(main_window, vat_combo, item.vat_percent, step="resolve_product")

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()

    # The SKU is what every later lookup of this product matches on, so a
    # SKU that did not persist makes the record unfindable and the next run
    # creates a duplicate. The price is checked for a different reason: it is
    # the one field Fakturama re-parses in its own locale, so it can persist
    # as a plausible but wrong number. Unverified, that reached the Order as a
    # wrong U.Price and was only caught two states later by the items grid -
    # after a bad Product record had already been saved.
    saved_fields = [
        resolver.SavedField(screens.PRODUCT_SKU_EDIT_NAME, item.sku, resolver.text_matches)
    ]
    if item.unit_net_price:
        saved_fields.append(
            resolver.SavedField(
                screens.PRODUCT_PRICE_GROSS_LABEL_NAME,
                _price_text(gross_price),
                resolver.money_matches,
                read=_read_price_text,
            )
        )
    resolver.verify_saved_fields(
        main_window,
        saved_fields,
        entity=f"product SKU '{item.sku}'",
        step="resolve_product",
        settle_seconds=settle_seconds,
    )
