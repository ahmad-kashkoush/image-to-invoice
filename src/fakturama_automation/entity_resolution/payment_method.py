from __future__ import annotations

from typing import Any

from fakturama_automation.entity_resolution import config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.ui_automation import controls, screens


def resolve_payment_method(
    app: Any,
    payment_method: str,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_payment_methods_list(main_window)
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


def _open_payment_methods_list(main_window: Any) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.PAYMENT_METHODS_NAV_NAME).click_input()


def _create_payment_method(
    main_window: Any,
    payment_method: str,
    *,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    # Only Name is filled; every other field on the form is optional.
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.PAYMENT_NEW_BUTTON_TITLE).click_input()

    controls.find_control(main_window, "Edit", name=screens.PAYMENT_NAME_EDIT_NAME).set_text(payment_method)

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()

    resolver.verify_saved_fields(
        main_window,
        [(screens.PAYMENT_NAME_EDIT_NAME, payment_method, resolver.text_matches)],
        entity=f"payment method '{payment_method}'",
        step="resolve_payment_method",
        settle_seconds=settle_seconds,
    )
