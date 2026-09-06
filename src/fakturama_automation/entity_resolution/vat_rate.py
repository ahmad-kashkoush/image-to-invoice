
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fakturama_automation.entity_resolution import config, matching, resolver
from fakturama_automation.entity_resolution.models import ResolvedEntity
from fakturama_automation.ui_automation import controls, screens


def resolve_vat_rate(
    app: Any,
    vat_percent: Decimal,
    *,
    client: Any = None,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> ResolvedEntity:
    main_window = app.main_window()

    def search_by() -> list[ResolvedEntity]:
        _open_vats_list(main_window)
        rows = resolver.search_grid_exact(
            main_window,
            grid_pane_name=screens.VATS_GRID_PANE_NAME,
            key=str(vat_percent),
            columns=screens.VATS_SEARCH_COLUMNS,
            vision_client=client,
            settle_seconds=settle_seconds,
        )
        matches = matching.exact_vat_matches(rows, vat_percent, read=lambda row: row[screens.VATS_SEARCH_COLUMNS[1]])
        return [ResolvedEntity(identity=f"{vat_percent}%", created=False) for _ in matches]

    def create() -> ResolvedEntity:
        _create_vat_rate(main_window, vat_percent, settle_seconds=settle_seconds)
        return ResolvedEntity(identity=f"{vat_percent}%", created=True)

    return resolver.resolve_exact_or_create(
        search_by, create, entity=f"VAT rate {vat_percent}%", step="resolve_vat_rate"
    )


def _open_vats_list(main_window: Any) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Text", name=screens.VATS_NAV_NAME).click_input()


def _create_vat_rate(
    main_window: Any,
    vat_percent: Decimal,
    *,
    settle_seconds: float = config.SEARCH_SETTLE_SECONDS,
) -> None:
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.VAT_NEW_BUTTON_TITLE).click_input()

    controls.find_control(main_window, "Edit", name=screens.VAT_NAME_EDIT_NAME).set_text(f"{vat_percent}%")

    value_edit = controls.find_control(main_window, "Edit", name=screens.VAT_VALUE_EDIT_NAME)
    controls.replace_text(value_edit, str(vat_percent))

    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=screens.SAVE_BUTTON_TITLE).click_input()

    resolver.verify_saved_fields(
        main_window,
        [
            (screens.VAT_NAME_EDIT_NAME, f"{vat_percent}%", resolver.text_matches),
            (screens.VAT_VALUE_EDIT_NAME, str(vat_percent), resolver.percent_matches),
        ],
        entity=f"VAT rate {vat_percent}%",
        step="resolve_vat_rate",
        settle_seconds=settle_seconds,
    )
