"""UI write actions the orchestrator's state machine composes.

Section 7 (orchestrator). Kept out of state_machine.py so the state loop
reads as control flow, not UI mechanics - the same split
entity_resolution.resolver draws between the search-then-create decision
and search_grid_exact's own control-driving half.

Never imports pywinauto: `app`/`window` are whatever duck-typed handles the
caller already holds (a FakturamaApp-like object exposing `.main_window()`,
and a pywinauto Pane/UIAWrapper for an open editor), the same testability
seam ui_automation.controls/entity_resolution.resolver already use
(Doc/adr/0002). Every write action composes ui_automation.controls with
either an already-pinned selector (entity_resolution.config/
verification.config) or one of this section's own orchestrator.config
selectors; the latter are explicit empty-string placeholders where no VM
probe exists yet, so a lookup against a real window fails closed
(ControlNotFoundError/AmbiguousControlError) rather than guessing - see
orchestrator/config.py and Doc/adr/0007-orchestrator.md.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.entity_resolution import config as entity_config
from fakturama_automation.entity_resolution import debtor, payment_method, product
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.orchestrator import config
from fakturama_automation.ui_automation import controls
from fakturama_automation.verification import comparisons
from fakturama_automation.verification import config as verification_config


def open_new_order(app: Any) -> Any:
    """Click "Create: New Order" on the main toolbar and return the new
    editor's own Pane (the same control verification.readback.window_title
    reads - titled "New Order" until saved, per
    verification/config.py's ORDER_TAB_TITLE_UNSAVED).
    """
    main_window = app.main_window()
    controls.find_control(main_window, "Button", name=config.NEW_ORDER_BUTTON_TITLE).click_input()
    return controls.find_control(
        main_window,
        "Pane",
        name=verification_config.ORDER_TAB_TITLE_UNSAVED,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )


def populate_order_fields(
    app: Any, window: Any, order: NormalizedOrder, *, client: Any = None, settle_seconds: float = config.SETTLE_SECONDS
) -> None:
    """Resolve the Debtor and Payment Method (search-then-create, Doc/
    Design.md's exact-match-only rule) and fill the Order's own Cust.Ref.
    field, then attach both resolved identities to this order.

    Attaching an already-resolved identity to *this* order is a distinct
    action from resolving it, with its own selector
    (config.ORDER_CUSTOMER_FIELD_AUTO_ID/ORDER_PAYMENT_METHOD_FIELD_AUTO_ID)
    that has no VM probe yet, so it fails closed here until one exists.
    """
    debtor.resolve_debtor(app, order, client=client, settle_seconds=settle_seconds)
    payment_method.resolve_payment_method(app, order.payment_method, client=client, settle_seconds=settle_seconds)

    cust_ref_edit = controls.find_control(window, "Edit", name=verification_config.ORDER_CUST_REF_EDIT_NAME)
    cust_ref_edit.set_text(order.external_reference)

    customer_field = controls.find_control(window, "Edit", auto_id=config.ORDER_CUSTOMER_FIELD_AUTO_ID)
    customer_field.set_text(order.debtor_company_name)

    payment_field = controls.find_control(window, "ComboBox", auto_id=config.ORDER_PAYMENT_METHOD_FIELD_AUTO_ID)
    payment_field.set_text(order.payment_method)


def add_order_line(
    app: Any,
    window: Any,
    item: NormalizedLineItem,
    *,
    client: Any = None,
    settle_seconds: float = config.SETTLE_SECONDS,
) -> None:
    """Resolve the line's Product by exact SKU (creating it, and its VAT
    rate if needed, per product.resolve_product), then enter it into the
    Order's own line grid.

    The grid is the same UIA-invisible custom-rendered canvas
    verification.config.ORDER_ITEMS_GRID_PANE_AUTO_ID reads from; entering
    a row into it needs an "add line" affordance no VM probe has captured
    yet (config.ORDER_LINE_ADD_BUTTON_TITLE), so this fails closed until
    one does.
    """
    product.resolve_product(app, item, client=client, settle_seconds=settle_seconds)
    controls.find_control(window, "Button", name=config.ORDER_LINE_ADD_BUTTON_TITLE).click_input()


def save_order(app: Any, window: Any) -> None:
    """Click the shared "Save the current contents" toolbar button (the
    same control every entity_resolution create form uses).

    `window` is accepted (unused) purely so every action in this module
    shares the same (app, window, ...) calling convention the state loop
    uses - the Save button itself is a main-toolbar control, not part of
    the editor pane.
    """
    main_window = app.main_window()
    controls.find_control(main_window, "Button", name=entity_config.SAVE_BUTTON_TITLE).click_input()


def create_linked_invoice(app: Any, order_window: Any, *, client: Any = None) -> Any:
    """Create the Invoice linked to order_window via Data > Documents and
    return its editor pane.

    No VM probe session has opened Data > Documents or a linked Invoice
    editor yet (verification/config.py has the identical gap for the
    Invoice editor's own fields) - config.INVOICE_FROM_ORDER_BUTTON_TITLE/
    INVOICE_EDITOR_PANE_NAME are explicit empty-string placeholders, so
    this fails closed at the first lookup until a probe fills them in.
    `client` is accepted for calling-convention symmetry with the other
    verify/create steps; not yet used since no vision-grounded read
    happens in this action today.
    """
    controls.find_control(order_window, "Button", name=config.INVOICE_FROM_ORDER_BUTTON_TITLE).click_input()
    return controls.find_control(
        app.main_window(),
        "Pane",
        name=config.INVOICE_EDITOR_PANE_NAME,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )


def apply_payment(app: Any, invoice_window: Any, order: NormalizedOrder, *, client: Any = None) -> None:
    """Set the Invoice's payment method and, if the order's extracted
    status is PAID, the payment date and full invoice value.

    Reuses verification.config's own placeholders for these controls
    (INVOICE_PAYMENT_METHOD_COMBO_NAME/INVOICE_PAID_CHECKBOX_NAME/
    INVOICE_PAYMENT_DATE_EDIT_NAME/INVOICE_PAYMENT_VALUE_EDIT_NAME) rather
    than duplicating them - Section 5 already established that none of
    these have a VM probe yet, so every lookup here fails closed the same
    way payment_verification.verify_payment_applied's read-back does.
    `app`/`client` are accepted for calling-convention symmetry; unused
    since payment fields live on invoice_window and no vision read is
    needed to set them.
    """
    method_combo = controls.find_control(
        invoice_window, "ComboBox", name=verification_config.INVOICE_PAYMENT_METHOD_COMBO_NAME
    )
    method_combo.set_text(order.payment_method)

    if order.payment_status.strip().upper() != "PAID":
        return

    paid_checkbox = controls.find_control(
        invoice_window, "CheckBox", name=verification_config.INVOICE_PAID_CHECKBOX_NAME
    )
    if paid_checkbox.get_toggle_state() != 1:
        paid_checkbox.click_input()

    if order.payment_date is not None:
        payment_date_edit = controls.find_control(
            invoice_window, "Edit", name=verification_config.INVOICE_PAYMENT_DATE_EDIT_NAME
        )
        payment_date_edit.set_text(order.payment_date.isoformat())

    _, _, gross_total = comparisons.order_level_totals(order)
    value_edit = controls.find_control(invoice_window, "Edit", name=verification_config.INVOICE_PAYMENT_VALUE_EDIT_NAME)
    value_edit.set_text(str(gross_total))
