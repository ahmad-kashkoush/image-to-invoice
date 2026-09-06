"""Debtor resolution: search Fakturama by exact company name, create a new
Debtor only if no exact match exists.

Control identifiers are pinned from live VM probes and live in
ui_automation/screens.py, the one selector inventory for every screen.
"""

from __future__ import annotations

import time
from typing import Any

from fakturama_automation.entity_resolution import combos, config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import controls, locators, screens


def resolve_debtor(
    app: Any,
    order: NormalizedOrder,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    """Resolve the debtor for a normalized order to a Fakturama record.

    `app` is a connected FakturamaApp-like handle (`.main_window()` only -
    every control here lives in Fakturama's single main window). `client`
    is the injectable vision client for reading the Debtors results grid.

    Matches by exact `order.debtor_company_name` only. Ambiguity (>1 exact
    match) raises ManualReviewRequired rather than picking one.
    """
    company_name = order.debtor_company_name
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
        matches = matching.exact_text_matches(rows, company_name, read=lambda row: row[screens.DEBTORS_SEARCH_COLUMNS[0]])
        return [ResolvedEntity(identity=company_name, created=False, element=row) for row in matches]

    def create() -> ResolvedEntity:
        element = _create_debtor(main_window, order, client=client, settle_seconds=settle_seconds)
        return ResolvedEntity(identity=company_name, created=True, element=element)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"debtor '{company_name}'", step="resolve_debtor"
    )


def _open_debtors_list(main_window: Any) -> None:
    """Select the Debtors list from the left Navigation View.

    The nav item renders as a UIA "Text" control, not a Button, so it's
    clicked via click_input() on its discovered bounding rect.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.DEBTORS_NAV_NAME).click_input()


def _create_debtor(
    main_window: Any,
    order: NormalizedOrder,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> Any:
    """Open the New Debtor form, fill it from the normalized order, save.

    Returns the Company edit control as the resolved record's `element` (a
    stable, re-findable reference; the editor tab/pane itself is
    unsuitable since its title and auto_id both change once data is
    entered). `client` is the injectable vision client for reading the
    Country combo's real options.

    `settle_seconds` is used once, after Street: setting ZIP/City
    immediately after Street raises a persistent COMError that
    `controls.set_text`'s own retry never recovers from, since Fakturama
    rebuilds the row's widgets out from under the already-fetched wrapper -
    a fresh lookup moments later finds a live Edit, so this settles before
    the ZIP/City lookup starts rather than retrying a stale reference.
    """
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.DEBTOR_NEW_BUTTON_TITLE).click_input()

    # type_text (real keystrokes), not set_text: set_text() silently fails
    # to persist this field through Save (see controls.type_text) - every
    # other field below keeps using set_text(), which works fine for them.
    company_edit = controls.find_control(main_window, "Edit", name=screens.DEBTOR_COMPANY_EDIT_NAME)
    controls.type_text(company_edit, order.debtor_company_name)

    if order.contact_name:
        first_name, _, last_name = order.contact_name.partition(" ")
        # Both Edits are blank-named, so located structurally: the label's
        # own next sibling is the Pane wrapping this row's two Edits,
        # left-to-right (First, then Last).
        name_pane = locators.sibling_pane_after_label(main_window, screens.DEBTOR_NAME_ROW_LABEL_NAME)
        first_name_edit, last_name_edit = name_pane.descendants(control_type="Edit")
        first_name_edit.set_text(first_name)
        last_name_edit.set_text(last_name)

    if order.alias:
        controls.find_control(main_window, "Edit", name=screens.DEBTOR_ALIAS_EDIT_NAME).set_text(order.alias)

    address = order.billing_address
    if address.street:
        controls.find_control(main_window, "Edit", name=screens.DEBTOR_STREET_EDIT_NAME).set_text(address.street)
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
    return company_edit
