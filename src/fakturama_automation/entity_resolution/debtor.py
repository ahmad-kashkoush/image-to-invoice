from __future__ import annotations

import time
from typing import Any

from fakturama_automation.entity_resolution import combos, config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import controls, locators, readers, screens


def resolve_debtor(
    app: Any,
    order: NormalizedOrder,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    company_name = order.debtor_company_name
    # Same partition(" ") idiom _create_debtor uses, so a created record and a
    # later match against it agree on what counts as First/Last Name.
    first_name, _, last_name = order.contact_name.partition(" ")
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_debtors_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            grid_pane_name=screens.DEBTORS_GRID_PANE_NAME,
            key=company_name,
            columns=screens.DEBTORS_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        no_col, first_col, last_col, company_col, zip_col, city_col = screens.DEBTORS_SEARCH_COLUMNS
        matches = matching.exact_debtor_matches(
            rows,
            company=company_name,
            first_name=first_name,
            last_name=last_name,
            zip_code=order.billing_address.postal_code,
            city=order.billing_address.city,
            company_column=company_col,
            first_name_column=first_col,
            last_name_column=last_col,
            zip_column=zip_col,
            city_column=city_col,
        )
        return [ResolvedEntity(identity=row[no_col], created=False) for row in matches]

    def create() -> ResolvedEntity:
        _create_debtor(main_window, order, client=client, settle_seconds=settle_seconds)
        customer_id = readers.read_field_text(main_window, name=screens.DEBTOR_CUSTOMER_ID_EDIT_NAME)
        return ResolvedEntity(identity=customer_id, created=True)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"debtor '{company_name}'", step="resolve_debtor"
    )


def _open_debtors_list(main_window: Any) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.DEBTORS_NAV_NAME).click_input()


def _create_debtor(
    main_window: Any,
    order: NormalizedOrder,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.DEBTOR_NEW_BUTTON_TITLE).click_input()

    controls.type_text(
        controls.find_control(main_window, "Edit", name=screens.DEBTOR_COMPANY_EDIT_NAME),
        order.debtor_company_name,
    )

    if order.contact_name:
        first_name, _, last_name = order.contact_name.partition(" ")
        name_pane = locators.sibling_pane_after_label(main_window, screens.DEBTOR_NAME_ROW_LABEL_NAME)
        first_name_edit, last_name_edit = name_pane.descendants(control_type="Edit")
        controls.set_text(first_name_edit, first_name)
        controls.set_text(last_name_edit, last_name)

    if order.alias:
        controls.set_text(
            controls.find_control(main_window, "Edit", name=screens.DEBTOR_ALIAS_EDIT_NAME), order.alias
        )

    address = order.billing_address
    if address.street:
        controls.set_text(
            controls.find_control(main_window, "Edit", name=screens.DEBTOR_STREET_EDIT_NAME), address.street
        )
        time.sleep(settle_seconds)
    if address.postal_code or address.city:
        # Both Edits are blank-named siblings under the "ZIP - City"
        # label's own sibling Pane, left-to-right (ZIP, then City) - same
        # pattern as the First/Last Name fields above.
        zip_city_pane = locators.sibling_pane_after_label(
            main_window, screens.DEBTOR_ZIP_CITY_ROW_LABEL_NAME
        )
        zip_edit, city_edit = zip_city_pane.descendants(control_type="Edit")
        if address.postal_code:
            controls.set_text(zip_edit, address.postal_code)
        if address.city:
            controls.set_text(city_edit, address.city)
    if address.country:
        # Selected by reading the combo's real, currently-open options and
        # clicking the matching one (combos.select_exact_option) - never a
        # guessed option string - so a mismatch (e.g. the combo shows full
        # country names while normalized data holds a code) fails closed
        # to manual review instead of raising a raw pywinauto error.
        country_combo = controls.find_control(main_window, "ComboBox", name=screens.DEBTOR_COUNTRY_COMBO_NAME)
        combos.select_exact_option(main_window, country_combo, address.country, client=client, step="resolve_debtor")

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()

    resolver.verify_saved_fields(
        main_window,
        [(screens.DEBTOR_COMPANY_EDIT_NAME, order.debtor_company_name, resolver.text_matches)],
        entity=f"debtor '{order.debtor_company_name}'",
        step="resolve_debtor",
        settle_seconds=settle_seconds,
    )
