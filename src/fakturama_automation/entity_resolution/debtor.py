"""Debtor resolution: search Fakturama by exact company name, create a new
Debtor only if no exact match exists.

Section 4 (entity_resolution). Control identifiers below are pinned from
probes/probe-06-debitors.txt (list/search view) and
probes/probe-03-create-debitor.txt / probe-04-fill-create-debitor.txt
(create form), all fully probed on the Windows 11 ARM VM - see
entity_resolution/config.py for the full selector inventory and its
provenance.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.entity_resolution import config, matching, resolver
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

    `app` is a connected FakturamaApp-like handle (only `.main_window()` is
    used - every control here lives in Fakturama's single Eclipse RCP main
    window, not a separate top-level dialog). `client` is the injectable
    vision client threaded through to resolver.search_grid_exact for
    reading the (UIA-invisible) Debtors results grid. `settle_seconds`
    overrides search_grid_exact's fixed post-search-type settle delay
    (tests pass 0; see resolver.search_grid_exact's docstring for why a
    delay is used at all).

    Matches by exact `order.debtor_company_name` only (Doc/Design.md: exact
    match, never fuzzy). Ambiguity (>1 exact match) raises
    ManualReviewRequired via resolver.resolve_exact_or_create rather than
    picking one.
    """
    company_name = order.debtor_company_name
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_debtors_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            search_edit_auto_id=config.DEBTOR_SEARCH_EDIT_AUTO_ID,
            grid_pane_auto_id=config.DEBTOR_LIST_PANE_AUTO_ID,
            key=company_name,
            columns=_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, company_name, read=lambda row: row["Company Name"])
        return [ResolvedEntity(identity=company_name, created=False, element=row) for row in matches]

    def create() -> ResolvedEntity:
        element = _create_debtor(main_window, order)
        return ResolvedEntity(identity=company_name, created=True, element=element)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"debtor '{company_name}'", step="resolve_debtor"
    )


def _open_debtors_list(main_window: Any) -> None:
    """Select the Debtors list from the left Navigation View.

    The nav item renders as a UIA "Text" control (confirmed:
    probes/probe-00-root.txt shows `child_window(title="Debtors",
    auto_id="721996", control_type="Text")`), not a Button, so it's clicked
    via click_input() (a geometry-grounded click on the discovered
    element's own bounding rect - not a hardcoded screen coordinate; see
    Doc/Design.md's control discovery section).
    """
    controls.find_control(main_window, "Text", name="Debtors").click_input()


def _create_debtor(main_window: Any, order: NormalizedOrder) -> Any:
    """Open the New Debtor form, fill it from the normalized order, save.

    Returns the Company edit control as the resolved record's `element`
    (a stable, re-findable reference; the editor tab/pane itself is
    unsuitable since its title and auto_id both change once data is
    entered - see entity_resolution/config.py's docstring).
    """
    controls.find_control(main_window, "Button", name=config.DEBTOR_NEW_BUTTON_TITLE).click_input()

    company_edit = controls.find_control(main_window, "Edit", auto_id=config.DEBTOR_FORM_COMPANY_AUTO_ID)
    company_edit.set_text(order.debtor_company_name)

    if order.contact_name:
        first_name, _, last_name = order.contact_name.partition(" ")
        controls.find_control(
            main_window, "Edit", auto_id=config.DEBTOR_FORM_FIRST_NAME_AUTO_ID
        ).set_text(first_name)
        controls.find_control(
            main_window, "Edit", auto_id=config.DEBTOR_FORM_LAST_NAME_AUTO_ID
        ).set_text(last_name)

    if order.alias:
        controls.find_control(main_window, "Edit", auto_id=config.DEBTOR_FORM_ALIAS_AUTO_ID).set_text(order.alias)

    address = order.billing_address
    if address.street:
        controls.find_control(main_window, "Edit", auto_id=config.DEBTOR_FORM_STREET_AUTO_ID).set_text(
            address.street
        )
    if address.postal_code:
        controls.find_control(main_window, "Edit", auto_id=config.DEBTOR_FORM_ZIP_AUTO_ID).set_text(
            address.postal_code
        )
    if address.city:
        controls.find_control(main_window, "Edit", auto_id=config.DEBTOR_FORM_CITY_AUTO_ID).set_text(address.city)
    if address.country:
        # ComboBox.select() requires an exact option string; Fakturama's
        # actual Country option strings were not enumerated during
        # probing (the combo was never opened) - see
        # .claude/plans/entity-resolution.md's "Remaining probe gap" item
        # 4. This is left to raise naturally (not swallowed) if the option
        # text doesn't match, per this codebase's fail-closed convention.
        controls.find_control(
            main_window, "ComboBox", auto_id=config.DEBTOR_FORM_COUNTRY_COMBO_AUTO_ID
        ).select(address.country)

    controls.find_control(main_window, "Button", name=config.SAVE_BUTTON_TITLE).click_input()
    return company_edit
