from __future__ import annotations

import time
from typing import Any

from fakturama_automation.entity_resolution import debtor, payment_method, product
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.orchestrator import config
from fakturama_automation.orchestrator.steps import items_grid, pickers, toolbar
from fakturama_automation.ui_automation import controls, locators, screens, vision_grounding

# Matches state_machine.WorkflowState.POPULATE_ORDER_FIELDS.value. Not
# imported from state_machine, which imports this package.
_POPULATE_STEP = "populate_order_fields"


def open_new_order(app: Any) -> Any:
    main_window = app.main_window()
    toolbar.click_new_order(main_window)
    return controls.find_control(
        main_window,
        "Pane",
        name=screens.ORDER_TAB_TITLE_UNSAVED,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )


def populate_order_fields(
    app: Any, window: Any, order: NormalizedOrder, *, client: Any = None, settle_seconds: float = config.SETTLE_SECONDS
) -> None:
    debtor.resolve_debtor(app, order, client=client, settle_seconds=settle_seconds)
    payment_method.resolve_payment_method(app, order.payment_method, client=client, settle_seconds=settle_seconds)

    # Resolution navigates the Navigation View away, and Eclipse stops
    # exposing a tab's content to UIA once you leave it - see
    # controls.reactivate_editor for why this is proved, not assumed.
    main_window = app.main_window()
    cust_ref_edit = _reactivate(main_window, window, "Edit", screens.ORDER_CUST_REF_EDIT_NAME)
    cust_ref_edit.set_text(order.external_reference)

    _set_pricing_mode_net(main_window)

    _attach_debtor_to_order(
        app, main_window, order.debtor_company_name, client=client, settle_seconds=settle_seconds
    )


def _reactivate(main_window: Any, window: Any, probe_type: str, probe_name: str) -> Any:
    return controls.reactivate_editor(
        main_window,
        window,
        probe_type=probe_type,
        probe_name=probe_name,
        attempts=config.EDITOR_ACTIVATE_ATTEMPTS,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )


def _set_pricing_mode_net(main_window: Any) -> None:
    mode_combo = locators.sibling_after_label(main_window, screens.ORDER_DATE_LABEL_NAME, offset=2)
    mode_combo.select(screens.ORDER_PRICING_MODE_NET_OPTION)


def _attach_debtor_to_order(
    app: Any,
    main_window: Any,
    company_name: str,
    *,
    client: Any = None,
    settle_seconds: float = config.SETTLE_SECONDS,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> None:
    controls.focus(main_window)
    attach_button = locators.sibling_after_label(
        main_window, screens.ORDER_ADDRESSES_LABEL_NAME, timeout_seconds=timeout_seconds
    )

    def _not_one_row_reason(count: int, rows: list[vision_grounding.GridRow]) -> str:
        found = (
            ", ".join(row.cells.get(screens.ORDER_SELECT_ADDRESS_COMPANY_COLUMN) or "<blank>" for row in rows)
            if rows
            else "none"
        )
        return (
            f"{count} rows in the \"{screens.ORDER_SELECT_ADDRESS_DIALOG_TITLE}\" dialog after searching for "
            f"'{company_name}' (expected exactly one); found: {found}"
        )

    pickers.pick_row_via_picker(
        app,
        main_window,
        attach_button,
        screens.ORDER_SELECT_ADDRESS_DIALOG_TITLE,
        key=company_name,
        columns=screens.ORDER_SELECT_ADDRESS_SEARCH_COLUMNS,
        client=client,
        settle_seconds=settle_seconds,
        timeout_seconds=timeout_seconds,
        step=_POPULATE_STEP,
        not_one_row_reason=_not_one_row_reason,
    )


def add_order_line(
    app: Any,
    window: Any,
    item: NormalizedLineItem,
    *,
    position: int,
    client: Any = None,
    settle_seconds: float = config.SETTLE_SECONDS,
) -> None:
    product.resolve_product(app, item, client=client, settle_seconds=settle_seconds)

    main_window = app.main_window()
    items_label = _reactivate(main_window, window, "Text", screens.ORDER_ITEMS_LABEL_NAME)
    pick_product_image = locators.sibling_after(items_label)

    pickers.pick_row_via_picker(
        app,
        main_window,
        pick_product_image,
        screens.ORDER_SELECT_PRODUCT_DIALOG_TITLE,
        key=item.sku,
        columns=screens.ORDER_SELECT_PRODUCT_SEARCH_COLUMNS,
        client=client,
        settle_seconds=settle_seconds,
        step=items_grid.ADD_LINES_STEP,
        not_one_row_reason=lambda count, rows: (
            f"{count} rows in the \"{screens.ORDER_SELECT_PRODUCT_DIALOG_TITLE}\" dialog after searching "
            f"for SKU '{item.sku}' (expected exactly one)"
        ),
    )
    # Wait for the close rather than a fixed settle: this dialog is reopened
    # once per line, and reopening before the previous instance has torn
    # down hands back a stale UIA tree.
    app.wait_until_top_level_window_closed(
        screens.ORDER_SELECT_PRODUCT_DIALOG_TITLE, timeout_seconds=config.DIALOG_TIMEOUT_SECONDS
    )
    time.sleep(settle_seconds)

    # items_label survives the dialog: a modal opened and closed over this
    # tab, it was never navigated away from.
    items_grid.fill_and_verify_line(
        main_window, items_label, item, position=position, client=client, settle_seconds=settle_seconds
    )


def save_order(app: Any, window: Any) -> None:
    main_window = app.main_window()
    controls.focus(main_window)
    toolbar.click_save(main_window)
