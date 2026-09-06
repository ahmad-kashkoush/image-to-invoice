"""Debtor resolution: search Fakturama by exact company name, create a new
Debtor only if no exact match exists.

Control identifiers below are pinned from live VM probes - see
entity_resolution/config.py for the full selector inventory.
"""

from __future__ import annotations

import time
from typing import Any

from fakturama_automation.entity_resolution import combos, config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.ui_automation import controls

_SEARCH_COLUMNS = ["Company Name"]


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
            grid_pane_name="Debtors",
            key=company_name,
            columns=_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, company_name, read=lambda row: row["Company Name"])
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
    controls.find_control(main_window, "Text", name="Debtors").click_input()


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
    controls.find_control(main_window, "Button", name=config.DEBTOR_NEW_BUTTON_TITLE).click_input()

    # type_text (real keystrokes), not set_text: set_text() silently fails
    # to persist this field through Save (see controls.type_text) - every
    # other field below keeps using set_text(), which works fine for them.
    company_edit = controls.find_control(main_window, "Edit", name="Company")
    controls.type_text(company_edit, order.debtor_company_name)

    if order.contact_name:
        first_name, _, last_name = order.contact_name.partition(" ")
        # Both Edits are blank-named, so located structurally: the label's
        # own next sibling is the Pane wrapping this row's two Edits,
        # left-to-right (First, then Last).
        name_label = controls.find_control(main_window, "Text", name="First Name Last Name")
        siblings = name_label.parent().children()
        name_pane = siblings[siblings.index(name_label) + 1]
        first_name_edit, last_name_edit = name_pane.descendants(control_type="Edit")
        first_name_edit.set_text(first_name)
        last_name_edit.set_text(last_name)

    if order.alias:
        controls.find_control(main_window, "Edit", name="additional name").set_text(order.alias)

    address = order.billing_address
    if address.street:
        controls.find_control(main_window, "Edit", name="Street").set_text(address.street)
        time.sleep(settle_seconds)
    if address.postal_code or address.city:
        # Both Edits are blank-named siblings under the "ZIP - City"
        # label's own sibling Pane, left-to-right (ZIP, then City) - same
        # pattern as the First/Last Name fields above.
        zip_city_label = controls.find_control(main_window, "Text", name="ZIP - City")
        siblings = zip_city_label.parent().children()
        zip_city_pane = siblings[siblings.index(zip_city_label) + 1]
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
        country_combo = controls.find_control(main_window, "ComboBox", name="Country")
        combos.select_exact_option(main_window, country_combo, address.country, client=client, step="resolve_debtor")

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=config.SAVE_BUTTON_TITLE).click_input()
    return company_edit
