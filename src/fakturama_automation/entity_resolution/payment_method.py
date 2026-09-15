from __future__ import annotations

import time
from typing import Any

from fakturama_automation.entity_resolution import config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation import controls, locators, screens, vision_grounding


def resolve_payment_method(
    app: Any,
    payment_method: str,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        resolver.open_list_screen(main_window, screens.PAYMENT_METHODS_NAV_NAME)
        rows = resolver.search_grid_exact(
            main_window,
            grid_pane_name=screens.PAYMENT_METHODS_GRID_PANE_NAME,
            key=payment_method,
            columns=screens.PAYMENT_METHODS_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_text_matches(rows, payment_method, read=lambda row: row[screens.PAYMENT_METHODS_SEARCH_COLUMNS[0]])
        return [ResolvedEntity(identity=payment_method, created=False) for _ in matches]

    def create() -> ResolvedEntity:
        _create_payment_method(main_window, payment_method, settle_seconds=settle_seconds)
        return ResolvedEntity(identity=payment_method, created=True)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"payment method '{payment_method}'", step="resolve_payment_method"
    )


def _create_payment_method(
    main_window: Any,
    payment_method: str,
    *,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    # Only Name is filled; every other field on the form is optional.
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.PAYMENT_NEW_BUTTON_TITLE).click_input()

    controls.set_text(
        controls.find_control(main_window, "Edit", name=screens.PAYMENT_NAME_EDIT_NAME), payment_method
    )

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()

    resolver.verify_saved_fields(
        main_window,
        [resolver.SavedField(screens.PAYMENT_NAME_EDIT_NAME, payment_method, resolver.text_matches)],
        entity=f"payment method '{payment_method}'",
        step="resolve_payment_method",
        settle_seconds=settle_seconds,
    )


# --- the profile's standard payment term -------------------------------
#
# A new Order inherits the standard Payment at construction, and Fakturama's
# Order editor exposes no control to change it afterwards - probed live
# 2026-09-15 on both an unsaved and a saved Order (74 descendants, three
# combos: pricing mode, VAT, Shipping; nothing named pay/term/paid). The
# Debtor's own payment term does not help either: the Northstar Debtor
# already carried 'Bank Transfer' while the Order it was attached to still
# came out as the standard 'Cash On Delivery', because the Order is built
# before the Debtor is attached and attaching does not re-apply it.
#
# So the standard is the only lever, and `orchestrator/steps/order_editor.py`
# uses it the narrow way: set it, create the Order, put the previous one
# back. The mutation lasts a few seconds rather than outliving the run,
# because the standard is a profile-wide default a person using Fakturama
# alongside this would not expect to change.


def standard_payment_name(
    app: Any,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> str | None:
    """The name of the term currently marked standard, or None if none is."""
    main_window = app.main_window()
    rows = _list_payment_methods(main_window, key="", client=client, settle_seconds=settle_seconds)
    for row in rows:
        if row.get(screens.PAYMENT_STANDARD_COLUMN, "").strip():
            return row.get(screens.PAYMENT_NAME_EDIT_NAME, "").strip()
    return None


def make_standard(
    app: Any,
    payment_method: str,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    """Mark `payment_method` as the profile's standard, and check that it took."""
    main_window = app.main_window()
    _open_payment_method_record(main_window, payment_method, client=client, settle_seconds=settle_seconds)

    controls.focus(main_window)
    controls.find_control(
        main_window, "Button", name=screens.PAYMENT_SET_STANDARD_BUTTON_TITLE
    ).click_input()
    time.sleep(settle_seconds)
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()
    time.sleep(settle_seconds)

    # Read it back off the list, not off the form: the form's button gives no
    # feedback, and an unverified "set the default" is exactly the kind of
    # silent no-op that produced the wrong Order payment in the first place.
    # Live, clicking this button on an unsaved record does nothing at all.
    actual = standard_payment_name(app, client=client, settle_seconds=settle_seconds)
    if actual != payment_method:
        raise ManualReviewRequired(
            "resolve_payment_method",
            f"tried to make '{payment_method}' the standard payment term, but the list still "
            f"shows {actual!r} as standard - a new Order would inherit the wrong term",
        )


def _list_payment_methods(
    main_window: Any, *, key: str, client: Any, settle_seconds: float
) -> list[dict[str, str]]:
    resolver.open_list_screen(main_window, screens.PAYMENT_METHODS_NAV_NAME)
    return resolver.search_grid_exact(
        main_window,
        grid_pane_name=screens.PAYMENT_METHODS_GRID_PANE_NAME,
        key=key,
        columns=screens.PAYMENT_METHODS_LIST_COLUMNS,
        vision_client=client,
        settle_seconds=settle_seconds,
    )


def _open_payment_method_record(
    main_window: Any, payment_method: str, *, client: Any, settle_seconds: float
) -> None:
    # Same shape as orchestrator/steps/pickers.py: filter the grid to one row,
    # then double-click where the vision read says that row is.
    resolver.open_list_screen(main_window, screens.PAYMENT_METHODS_NAV_NAME)
    grid_pane = controls.find_control(
        main_window, "Pane", name=screens.PAYMENT_METHODS_GRID_PANE_NAME,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )
    label = locators.search_label(main_window, timeout_seconds=config.DIALOG_TIMEOUT_SECONDS)
    controls.set_text(locators.search_edit(label, timeout_seconds=config.DIALOG_TIMEOUT_SECONDS), payment_method)
    time.sleep(settle_seconds)

    controls.focus_foreground(main_window)
    controls.move_pointer_away(main_window)
    rows = vision_grounding.read_grid_rows_located(
        vision_grounding.capture_control_image(grid_pane),
        columns=screens.PAYMENT_METHODS_LIST_COLUMNS,
        client=client,
    )
    exact = [
        row for row in rows
        if row.cells.get(screens.PAYMENT_NAME_EDIT_NAME, "").strip() == payment_method
    ]
    if len(exact) != 1:
        raise ManualReviewRequired(
            "resolve_payment_method",
            f"{len(exact)} row(s) named '{payment_method}' in the terms-of-payment list "
            f"(expected exactly one, out of {len(rows)} row(s) read) - cannot open it to set the standard",
        )

    bounds = grid_pane.rectangle()
    x, y, width, height = exact[0].bbox
    point = (bounds.left + x + width // 2, bounds.top + y + height // 2)
    controls.focus(main_window)
    main_window.double_click_input(coords=point, absolute=True)
    time.sleep(settle_seconds)
