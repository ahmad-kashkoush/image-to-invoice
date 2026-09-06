"""UI write actions the orchestrator's state machine composes.

Kept out of state_machine.py so the state loop reads as control flow, not
UI mechanics.

Never imports pywinauto: `app`/`window` are whatever duck-typed handles the
caller already holds. Every write action composes ui_automation.controls
with either an already-pinned selector (entity_resolution.config/
verification.config) or one of this section's own orchestrator.config
selectors.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from fakturama_automation.entity_resolution import config as entity_config
from fakturama_automation.entity_resolution import debtor, payment_method, product
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.orchestrator import config
from fakturama_automation.ui_automation import controls, vision_grounding
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError, DialogTimeoutError
from fakturama_automation.verification import comparisons, readback
from fakturama_automation.verification import config as verification_config


def open_new_order(app: Any) -> Any:
    """Click "Create: New Order" on the main toolbar and return the new
    editor's own Pane (the same control verification.readback.window_title
    reads - titled "New Order" until saved, per
    verification/config.py's ORDER_TAB_TITLE_UNSAVED).
    """
    main_window = app.main_window()
    controls.focus(main_window)
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
    """Resolve the Debtor and Payment Method (search-then-create, exact-
    match-only), fill the Order's own Cust.Ref. field, then attach the
    resolved Debtor to this order.

    There is no Payment Method field on the Order screen at all -
    resolve_payment_method is still called here so the record exists in
    Fakturama by the time apply_payment sets the Invoice's payment-method
    combo by text, but nothing on this screen reads its result.
    """
    debtor.resolve_debtor(app, order, client=client, settle_seconds=settle_seconds)
    payment_method.resolve_payment_method(app, order.payment_method, client=client, settle_seconds=settle_seconds)

    # Re-select this Order's own tab before touching its fields: Eclipse
    # stops exposing a tab's content to UI Automation once you've navigated
    # away from it (Debtor/Payment Method resolution both switch the
    # Navigation View away). window.set_focus() on the already-held Pane
    # reference, not a fresh find_control(TabItem, name=...): re-finding by
    # title breaks (AmbiguousControlError) as soon as more than one
    # same-titled Order tab is open (e.g. a prior run's own never-saved
    # draft), which the reference-based approach sidesteps entirely.
    main_window = app.main_window()
    controls.focus(main_window)
    window.set_focus()

    cust_ref_edit = controls.find_control(main_window, "Edit", name=verification_config.ORDER_CUST_REF_EDIT_NAME)
    cust_ref_edit.set_text(order.external_reference)

    _set_pricing_mode_net(main_window)

    _attach_debtor_to_order(
        app, main_window, order.debtor_company_name, client=client, settle_seconds=settle_seconds
    )


def _set_pricing_mode_net(main_window: Any) -> None:
    """Switch the Order's pricing mode from its "Gross" default to "Net".

    Every price entered by this codebase is actually a net price (this
    project's money convention) - left on "Gross", the Order treats
    U.Price entries as gross-inclusive and extracts VAT backward out of
    them, producing silently wrong totals with no error raised. Not
    optional, not a preference.
    """
    date_label = controls.find_control(main_window, "Text", name=config.ORDER_DATE_LABEL_NAME)
    siblings = date_label.parent().children()
    mode_combo = siblings[siblings.index(date_label) + 2]
    mode_combo.select(config.ORDER_PRICING_MODE_NET_OPTION)


def _attach_debtor_to_order(
    app: Any,
    main_window: Any,
    company_name: str,
    *,
    client: Any = None,
    settle_seconds: float = config.SETTLE_SECONDS,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> None:
    """Attach the already-resolved Debtor identified by company_name to
    the currently-active Order editor, via its "Select the address"
    picker.

    The Order's customer field is a multi-line address Edit; you attach a
    Debtor by clicking a small blank-named Image just to its left
    (located structurally next to config.ORDER_ADDRESSES_LABEL_NAME),
    which opens a genuinely separate top-level OS window titled "Select
    the address" (app.top_level_window_by_title, not controls.find_control).

    Deliberately does NOT verify an exact text match on the Company cell
    the way every other resolver's search does: that column can render too
    narrow to show the full value, so a cell-text equality check against
    the untruncated target can never pass even when the row is correct.
    Instead this trusts Fakturama's own Search filtering and requires
    exactly one row after searching - fail closed on zero or more than
    one. Narrower than every other resolver's independent exact-match
    verification - see TODo.md's Future work for the more correct fix
    (match by the Debtor's own unique No./Customer ID instead of company
    name, which doesn't get clipped).
    """
    controls.focus(main_window)
    addresses_label = controls.find_control(
        main_window, "Text", name=config.ORDER_ADDRESSES_LABEL_NAME, timeout_seconds=timeout_seconds
    )
    siblings = addresses_label.parent().children()
    attach_button = siblings[siblings.index(addresses_label) + 1]

    def _not_one_row_reason(count: int, rows: list[vision_grounding.GridRow]) -> str:
        found = ", ".join(row.cells.get("Company") or "<blank>" for row in rows) if rows else "none"
        return (
            f"{count} rows in the \"Select the address\" dialog after searching for "
            f"'{company_name}' (expected exactly one); found: {found}"
        )

    _pick_row_via_picker(
        app,
        main_window,
        attach_button,
        config.ORDER_SELECT_ADDRESS_DIALOG_TITLE,
        key=company_name,
        columns=config.ORDER_SELECT_ADDRESS_SEARCH_COLUMNS,
        client=client,
        settle_seconds=settle_seconds,
        timeout_seconds=timeout_seconds,
        step="populate_order_fields",
        not_one_row_reason=_not_one_row_reason,
    )


def add_order_line(
    app: Any,
    window: Any,
    item: NormalizedLineItem,
    *,
    client: Any = None,
    settle_seconds: float = config.SETTLE_SECONDS,
) -> None:
    """Resolve the line's Product by exact SKU (creating it, and its VAT
    rate if needed, per product.resolve_product), add it to the Order's
    own line grid via the "Select a product" picker, then fill in Qty./
    Discount (the two per-line values the catalog record doesn't carry).

    The first Items-toolbar Image (not the green "add blank row" Image
    next to it) opens a "Select a product" picker, structurally identical
    to _attach_debtor_to_order's "Select the address" picker. Picking a
    row here and clicking OK inserts a row with Item No./Name/Description/
    Price/VAT already filled in from the Product's own catalog record -
    avoiding the fragile alternative (a blank row filled cell-by-cell) this
    replaced, which hit three separate live bugs in one run (an unprobed
    popup editor for Name, an unreliable VAT dropdown, confused cell
    positions across columns).

    Only Qty. and Discount remain to fill after the pick, since the
    catalog record has no notion of a specific order's quantity or
    discount - Fakturama visually highlights the newly-added row,
    vision_grounding.read_active_row_cells locates its per-column cells,
    and `_fill_grid_text_cell` commits each value.

    `window` (the New Order editor's own Pane from open_new_order) is used
    to re-select this specific Order's tab after resolving the Product -
    not otherwise read.
    """
    product.resolve_product(app, item, client=client, settle_seconds=settle_seconds)

    main_window = app.main_window()
    controls.focus(main_window)
    # Re-select this Order's own tab: resolving the Product switches the
    # Navigation View away from it, same reason populate_order_fields
    # re-selects it after resolving the Debtor/Payment Method - see that
    # function's own comment for why this uses window.set_focus() on the
    # already-held Pane reference, not a fresh find_control(TabItem, ...).
    window.set_focus()

    items_label = controls.find_control(main_window, "Text", name=config.ORDER_ITEMS_LABEL_NAME)
    toolbar_siblings = items_label.parent().children()
    pick_product_image = toolbar_siblings[toolbar_siblings.index(items_label) + 1]

    _pick_row_via_picker(
        app,
        main_window,
        pick_product_image,
        config.ORDER_SELECT_PRODUCT_DIALOG_TITLE,
        key=item.sku,
        columns=config.ORDER_SELECT_PRODUCT_SEARCH_COLUMNS,
        client=client,
        settle_seconds=settle_seconds,
        step="add_order_lines",
        not_one_row_reason=lambda count, rows: (
            f"{count} rows in the \"Select a product\" dialog after searching for SKU "
            f"'{item.sku}' (expected exactly one)"
        ),
    )
    # Wait for the picker to fully close, not just a fixed settle: add_
    # order_line reopens this same dialog once per line item, and
    # reopening before the previous instance has finished closing can hand
    # back a stale/half-torn-down UIA tree - see
    # app.wait_until_top_level_window_closed's own docstring.
    app.wait_until_top_level_window_closed(
        config.ORDER_SELECT_PRODUCT_DIALOG_TITLE, timeout_seconds=config.DIALOG_TIMEOUT_SECONDS
    )
    time.sleep(settle_seconds)

    # The dialog closing doesn't invalidate items_label/its toolbar - the
    # New Order tab was never navigated away from (a modal dialog opened
    # and closed on top of it, not a tab switch), so the reference from
    # before opening it is still good.
    grid_pane = readback.items_grid_pane(main_window, items_label=items_label)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    cells = vision_grounding.read_active_row_cells(
        image_bytes, columns=config.ORDER_LINE_GRID_QTY_DISCOUNT_COLUMNS, client=client
    )
    row_bounds = grid_pane.rectangle()

    def screen_point_for(column: str) -> tuple[int, int]:
        cx, cy, cwidth, cheight = cells[column]
        return (row_bounds.left + cx + cwidth // 2, row_bounds.top + cy + cheight // 2)

    _fill_grid_text_cell(main_window, screen_point_for("Qty."), str(item.quantity))
    _fill_grid_text_cell(main_window, screen_point_for("Discount"), str(item.discount))


def _pick_row_via_picker(
    app: Any,
    main_window: Any,
    open_button: Any,
    dialog_title: str,
    *,
    key: str,
    columns: list[str],
    client: Any,
    settle_seconds: float,
    step: str,
    not_one_row_reason: Callable[[int, list[Any]], str],
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
    stabilize_seconds: float = config.DIALOG_STABILIZE_SECONDS,
    attempts: int = config.DIALOG_OPEN_ATTEMPTS,
) -> None:
    """Open dialog_title via open_button and pick the single row matching
    key, retrying the *whole* open-search-pick cycle - not just the open -
    up to `attempts` times on a transient UI-discovery failure.

    Confirmed live: the picker dialog can flash open-and-close not only
    right after the toolbar click (the race _open_picker_dialog's own
    stabilize/content-probe already retries) but also *during* the
    subsequent search/read/click sequence in _pick_single_row_in_dialog,
    well after that first check already passed. This is genuinely
    intermittent, not deterministic - two back-to-back live attempts with
    identical inputs (same SKU, same order state) reproduced one failure
    and one clean success, ruling out a fixed logic bug in favor of a
    timing race that can land anywhere in the interaction, not only at
    open time. So this wraps the entire cycle as one retryable unit:
    _open_picker_dialog runs with attempts=1 (its own internal retry would
    otherwise multiply against this outer one), and a
    ControlNotFoundError/DialogTimeoutError from *either* step means "this
    attempt's dialog instance is gone", not a hard failure - the whole
    cycle (re-click included) is retried fresh. Before retrying, closes
    any dialog left open from the failed attempt (Escape) so the next
    open_button click can't collide with a stale leftover window of the
    same title (app.top_level_window_by_title fails closed on >1 match).

    ManualReviewRequired - a real "zero or many rows" business outcome
    from _pick_single_row_in_dialog, not a UI race - is never retried; it
    propagates immediately.
    """
    last_error: Exception
    for attempt in range(attempts):
        try:
            dialog = _open_picker_dialog(
                app, main_window, open_button, dialog_title, timeout_seconds=timeout_seconds,
                stabilize_seconds=stabilize_seconds, attempts=1,
            )
            controls.focus(dialog)
            _pick_single_row_in_dialog(
                dialog, key=key, columns=columns, client=client, settle_seconds=settle_seconds,
                step=step, not_one_row_reason=not_one_row_reason, timeout_seconds=timeout_seconds,
            )
            return
        except (ControlNotFoundError, DialogTimeoutError) as exc:
            last_error = exc
            if app.top_level_window_is_open(dialog_title):
                try:
                    stray = app.top_level_window_by_title(dialog_title, timeout_seconds=stabilize_seconds)
                    stray.type_keys("{ESC}")
                    app.wait_until_top_level_window_closed(dialog_title, timeout_seconds=timeout_seconds)
                except Exception:  # noqa: BLE001 - best-effort cleanup before the next retry
                    pass
            continue
    raise last_error


def _open_picker_dialog(
    app: Any,
    main_window: Any,
    open_button: Any,
    dialog_title: str,
    *,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
    stabilize_seconds: float = config.DIALOG_STABILIZE_SECONDS,
    attempts: int = config.DIALOG_OPEN_ATTEMPTS,
) -> Any:
    """Click open_button and return the dialog_title top-level window it
    opens, re-clicking if the dialog flashes open and closes again before
    the caller gets to use it.

    Both picker dialogs can appear and then vanish again within a fraction
    of a second of the toolbar click that opens them (confirmed live, root
    cause not fully isolated - likely an input race with the dialog's own
    initial render/focus). This re-checks app.top_level_window_is_open
    stabilize_seconds later before trusting the dialog, and re-clicks
    open_button (up to `attempts` times) if it's already gone by then -
    still failing closed if every attempt hits this.

    Window-visible isn't content-ready: confirmed live, reopening the same
    picker for a second order line can pass the window-visibility check
    above and still not have its "Search:" box (or any other child
    control) rendered yet - the same flash-open-close race, just landing
    after this function's own visibility check instead of before it. So
    this also probes for the dialog's own "Search:" Text control (short
    stabilize_seconds timeout, not the caller's full timeout_seconds) once
    the window looks stable, and retries the same way if that's missing
    too, rather than handing back a dialog whose content isn't there yet.
    """
    last_error: Exception
    for attempt in range(attempts):
        controls.focus(main_window)
        open_button.click_input()
        try:
            dialog = app.top_level_window_by_title(dialog_title, timeout_seconds=timeout_seconds)
        except DialogTimeoutError as exc:
            last_error = exc
            continue
        time.sleep(stabilize_seconds)
        if not app.top_level_window_is_open(dialog_title):
            last_error = ControlNotFoundError(
                f"{dialog_title!r} dialog closed again within {stabilize_seconds}s of opening "
                f"(attempt {attempt + 1}/{attempts})"
            )
            continue
        try:
            controls.find_control(dialog, "Text", name="Search:", timeout_seconds=stabilize_seconds)
        except ControlNotFoundError as exc:
            last_error = exc
            continue
        return dialog
    raise last_error


def _pick_single_row_in_dialog(
    dialog: Any,
    *,
    key: str,
    columns: list[str],
    client: Any,
    settle_seconds: float,
    step: str,
    not_one_row_reason: Callable[[int, list[Any]], str],
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> None:
    """Type `key` into dialog's "Search:" box, read the UIA-invisible
    results grid via vision_grounding, and click the single matching row
    then OK. Shared by _attach_debtor_to_order's "Select the address"
    picker and add_order_line's "Select a product" picker - structurally
    identical dialogs.

    Raises ManualReviewRequired(step, not_one_row_reason(count, rows)) if
    the grid doesn't show exactly one row after searching.
    """
    search_label = controls.find_control(dialog, "Text", name="Search:", timeout_seconds=timeout_seconds)
    search_edit = controls.find_control(search_label.parent(), "Edit", timeout_seconds=timeout_seconds)
    search_edit.set_text(key)
    time.sleep(settle_seconds)

    # search_label re-found fresh, not the pre-typing reference: typing can
    # rebuild the dialog's widget tree as it filters results, breaking that
    # reference's own .parent() chain even though the search itself worked.
    search_label = controls.find_control(dialog, "Text", name="Search:", timeout_seconds=timeout_seconds)
    grid_pane = _picker_grid_pane(search_label)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    rows = vision_grounding.read_grid_rows_located(image_bytes, columns=columns, client=client)
    if len(rows) != 1:
        raise ManualReviewRequired(step, not_one_row_reason(len(rows), rows))

    bounds = grid_pane.rectangle()
    x, y, width, height = rows[0].bbox
    screen_point = (bounds.left + x + width // 2, bounds.top + y + height // 2)
    # Fresh focus() before every click: read_grid_rows_located above is a
    # real network call (seconds), long enough for OS foreground focus to
    # drift away from Fakturama in between.
    controls.focus(dialog)
    dialog.click_input(coords=screen_point, absolute=True)
    controls.focus(dialog)
    controls.find_control(dialog, "Button", name=config.ORDER_PICKER_OK_BUTTON_TITLE).click_input()


def _picker_grid_pane(search_label: Any) -> Any:
    """A picker dialog's results grid Pane, three Panes up from its
    "Search:" label - its own parent Pane, then two more, whose second
    child is the grid body. Shared structure for both the "Select the
    address" and "Select a product" pickers.

    Walks the chain one hop at a time rather than a bare
    `search_label.parent().parent().parent()`, raising ControlNotFoundError
    (not a raw AttributeError) if any hop comes back None - defense in
    depth against a stale/half-torn-down UIA tree from reopening a picker
    before the previous instance fully closed (the actual fix is waiting
    for the close - see app.wait_until_top_level_window_closed).
    """
    node = search_label
    for hop in range(3):
        node = node.parent()
        if node is None:
            raise ControlNotFoundError(
                f"picker grid Pane lookup broke {hop + 1} parent() hop(s) up from the Search label - "
                "likely a stale/half-torn-down UIA tree"
            )
    return node.children()[1]


def _fill_grid_text_cell(main_window: Any, point: tuple[int, int], value: str) -> None:
    """Click a grid cell to select it, then type value directly: Ctrl+A
    (select whatever it already holds) + Delete, then the value, then Tab
    to commit.

    This grid's cells don't need - and don't reliably expose - a separate
    inline Edit control to interact with (confirmed live: a
    double-click-then-find-the-inline-editor approach could time out
    entirely, even though the cell visibly showed an edit-look caret). A
    single click to select the cell, followed by keyboard input straight
    to main_window with no Edit-lookup step, reproduces the same edit
    state and commits correctly every time.
    """
    controls.focus(main_window)
    main_window.click_input(coords=point, absolute=True)
    main_window.type_keys("^a{DELETE}")
    main_window.type_keys(controls.escape_send_keys(value), with_spaces=True)
    main_window.type_keys("{TAB}")


def save_order(app: Any, window: Any) -> None:
    """Click the shared "Save the current contents" toolbar button (the
    same control every entity_resolution create form uses).

    `window` is accepted (unused) purely so every action in this module
    shares the same (app, window, ...) calling convention the state loop
    uses - the Save button itself is a main-toolbar control, not part of
    the editor pane.
    """
    main_window = app.main_window()
    controls.focus(main_window)
    controls.find_control(main_window, "Button", name=entity_config.SAVE_BUTTON_TITLE).click_input()


def create_linked_invoice(app: Any, order_window: Any, *, client: Any = None) -> Any:
    """Create the Invoice linked to order_window and return its editor pane.

    Not a "Data > Documents" flow: the saved Order's own "Create a
    follow-up document" panel has an "Invoice" button directly
    (config.INVOICE_FROM_ORDER_BUTTON_TITLE). Clicking it opens a new tab,
    auto-activated, titled "New Invoice" until saved - inherits the
    Order's pricing mode, no separate switch needed here. `order_window.
    set_focus()` first, the same re-activate-before-touching-it precaution
    populate_order_fields/add_order_line apply, since neither
    save_order/verify_order_saved guarantees order_window is still the
    active tab by the time this runs. `client` is accepted for
    calling-convention symmetry; not yet used here.
    """
    controls.focus(app.main_window())
    order_window.set_focus()
    controls.find_control(order_window, "Button", name=config.INVOICE_FROM_ORDER_BUTTON_TITLE).click_input()
    return controls.find_control(
        app.main_window(),
        "Pane",
        name=config.INVOICE_EDITOR_PANE_NAME,
        timeout_seconds=config.DIALOG_TIMEOUT_SECONDS,
    )


def apply_payment(app: Any, invoice_window: Any, order: NormalizedOrder, *, client: Any = None) -> None:
    """Set the Invoice's payment method and, if the order's extracted
    status is PAID, check "paid" and fill in the payment date and full
    invoice value.

    Only the "paid" checkbox and "Value" have a stable accessible name -
    the payment-method combo and payment-date Edit are blank-named,
    located structurally instead via verification.readback's
    payment_method_combo/payment_date_edit helpers (shared with
    payment_verification.py's own read-back of the same fields). Checking
    "paid" is what makes the date/Value fields exist in the UI tree at
    all, so both lookups below happen after that click.

    The payment method combo is set via .select(), not set_text():
    clicking its option by screen coordinate is unreliable (confirmed
    live), while .select() worked directly every time. Date/Value are
    filled via controls.type_text (real keystrokes): both are
    freshly-appeared fields, the same class this codebase has repeatedly
    found needs real keystrokes to persist.
    """
    method_combo = readback.payment_method_combo(invoice_window)
    method_combo.select(order.payment_method)

    if order.payment_status.strip().upper() != "PAID":
        return

    paid_checkbox = controls.find_control(
        invoice_window, "CheckBox", name=verification_config.INVOICE_PAID_CHECKBOX_NAME
    )
    if paid_checkbox.get_toggle_state() != 1:
        controls.focus(app.main_window())
        paid_checkbox.click_input()

    if order.payment_date is not None:
        date_edit = readback.payment_date_edit(invoice_window)
        controls.type_text(date_edit, order.payment_date.isoformat())

    _, _, gross_total = comparisons.order_level_totals(order)
    value_edit = controls.find_control(invoice_window, "Edit", name=verification_config.INVOICE_PAYMENT_VALUE_EDIT_NAME)
    controls.type_text(value_edit, str(gross_total))
