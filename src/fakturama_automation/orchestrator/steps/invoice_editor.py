from __future__ import annotations

from typing import Any

from fakturama_automation.normalization.models import NormalizedOrder
from fakturama_automation.orchestrator import config
from fakturama_automation.orchestrator.steps import toolbar
from fakturama_automation.ui_automation import controls, locators, screens
from fakturama_automation.verification import comparisons


def create_linked_invoice(app: Any, order_window: Any, *, client: Any = None) -> Any:
    controls.focus(app.main_window())
    order_window.set_focus()
    controls.find_control(
        order_window, "Button", name=screens.INVOICE_FROM_ORDER_BUTTON_TITLE
    ).click_input()
    return controls.find_control(
        app.main_window(),
        "Pane",
        name=screens.INVOICE_TAB_TITLE_UNSAVED,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )


def apply_payment(app: Any, invoice_window: Any, order: NormalizedOrder, *, client: Any = None) -> None:
    method_combo = locators.payment_method_combo(invoice_window)
    method_combo.select(order.payment_method)

    if not order.is_paid:
        return

    paid_checkbox = controls.find_control(
        invoice_window, "CheckBox", name=screens.INVOICE_PAID_CHECKBOX_NAME
    )
    if paid_checkbox.get_toggle_state() != 1:
        controls.focus(app.main_window())
        paid_checkbox.click_input()

    if order.payment_date is not None:
        date_edit = locators.payment_date_edit(invoice_window)
        controls.replace_text(date_edit, order.payment_date.isoformat())

    _, _, gross_total = comparisons.order_level_totals(order)
    value_edit = controls.find_control(
        invoice_window, "Edit", name=screens.INVOICE_PAYMENT_VALUE_EDIT_NAME
    )
    controls.replace_text(value_edit, str(gross_total))


def save_invoice(app: Any, invoice_window: Any) -> None:
    # Unlike save_order this cannot just click: Save acts on whichever editor
    # is active, and by now the Order editor is also open and verification has
    # been reading controls in between. Probing for the Invoice's Cust.Ref. is
    # unambiguous despite the Order having the same field, because Eclipse only
    # exposes the active tab's contents to UIA.
    #
    # Saving is what creates the Invoice row - payment applied to an unsaved
    # editor never reached the database at all.
    main_window = app.main_window()
    controls.reactivate_editor(
        main_window,
        invoice_window,
        probe_type="Edit",
        probe_name=screens.INVOICE_CUST_REF_EDIT_NAME,
        attempts=config.EDITOR_ACTIVATE_ATTEMPTS,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )
    toolbar.click_save(main_window)
