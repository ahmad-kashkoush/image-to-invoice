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
from fakturama_automation.ui_automation import controls, grid_geometry, vision_grounding
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError, DialogTimeoutError
from fakturama_automation.verification import comparisons, readback
from fakturama_automation.verification import config as verification_config

# Matches state_machine.WorkflowState.ADD_ORDER_LINES.value, so a line-entry
# problem raised here and one raised by the state loop land in the manual
# review queue under the same step.
_ADD_LINES_STEP = "add_order_lines"


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
    cust_ref_edit = _reactivate_editor(
        main_window, window, probe_name=verification_config.ORDER_CUST_REF_EDIT_NAME
    )
    cust_ref_edit.set_text(order.external_reference)

    _set_pricing_mode_net(main_window)

    _attach_debtor_to_order(
        app, main_window, order.debtor_company_name, client=client, settle_seconds=settle_seconds
    )


def _reactivate_editor(
    main_window: Any,
    window: Any,
    *,
    probe_name: str,
    probe_type: str = "Edit",
    attempts: int = config.EDITOR_ACTIVATE_ATTEMPTS,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> Any:
    """Re-select the editor tab `window` and return one of its own controls,
    confirming its content is actually exposed again.

    Eclipse stops exposing a tab's content to UI Automation once you
    navigate away from it, and entity resolution navigates away every time
    (the Debtor/Product/Payment lists are other tabs). `set_focus()` on the
    held Pane reference is what brings it back - but it can silently not
    take, and then the very next lookup fails with "no Edit control named
    'Cust.Ref.' found", as if the editor were gone. Observed live, and
    increasingly likely as leftover editor tabs pile up from earlier runs.

    So the activation is retried until a control that only exists inside
    this editor can be found, rather than assumed to have worked. Retrying
    is safe: `set_focus()` selects a tab, it doesn't change anything in the
    document.
    """
    last_error: ControlNotFoundError | None = None
    for _attempt in range(attempts):
        controls.focus(main_window)
        window.set_focus()
        try:
            return controls.find_control(
                main_window, probe_type, name=probe_name, timeout_seconds=timeout_seconds
            )
        except ControlNotFoundError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


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
    position: int,
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

    `_fill_and_verify_line_cells` then fills the cells the pick doesn't
    reliably supply - Qty./Discount (the catalog record has no per-order
    quantity or discount) and Item No. (see config.ORDER_LINE_GRID_FILL_
    COLUMNS: the picked row can carry an internal record number there
    instead of the SKU) - locating the row by its `position` and reading
    it back to confirm every value landed.

    `position` is the line's 1-based position in the order, which is also
    what the grid's Pos. column shows, since the state machine adds lines
    in order.

    `window` (the New Order editor's own Pane from open_new_order) is used
    to re-select this specific Order's tab after resolving the Product -
    not otherwise read.
    """
    product.resolve_product(app, item, client=client, settle_seconds=settle_seconds)

    main_window = app.main_window()
    # Re-select this Order's own tab: resolving the Product switches the
    # Navigation View away from it, same reason populate_order_fields
    # re-selects it after resolving the Debtor/Payment Method - and
    # confirmed the same way, by finding a control that only exists inside
    # this editor (see _reactivate_editor).
    items_label = _reactivate_editor(
        main_window, window, probe_name=config.ORDER_ITEMS_LABEL_NAME, probe_type="Text"
    )
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
        step=_ADD_LINES_STEP,
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
    _fill_and_verify_line_cells(
        main_window, items_label, item, position=position, client=client, settle_seconds=settle_seconds
    )


def _fill_and_verify_line_cells(
    main_window: Any,
    items_label: Any,
    item: NormalizedLineItem,
    *,
    position: int,
    client: Any,
    settle_seconds: float,
    attempts: int = config.ORDER_LINE_FILL_ATTEMPTS,
) -> None:
    """Fill the just-added line's Item No./Qty./Discount cells, then read
    the whole row back and confirm it matches the line item - retrying the
    fill from a freshly-located row, and failing closed if it still doesn't
    take.

    Both halves of this exist because a live run wrote a line's Qty.
    into nowhere and said nothing: the second line item's quantity stayed
    at Fakturama's default 1.00 while the first line's 2 landed, and the
    run carried on to save an order that was simply wrong. There is no UIA
    row/column structure in this grid, so a cell is written by clicking a
    screen coordinate computed from a vision read of a screenshot - a write
    that can miss the cell entirely, and, typed into no focused editor,
    leaves no trace.

    Cells are located by measuring the grid's own separator lines
    (ui_automation.grid_geometry) and counting columns off them, with the
    row taken from `position` - lines are added in order, so the caller
    already knows which row it just added. Neither half is guessed: not
    Fakturama's highlight (the original anchor, a guess about the app's
    selection state), and not a vision read of the cell boxes (the next
    thing tried, and measurably wrong - it put a line's quantity in the
    Item No. column and its discount in the Name column, live).

    The read-back reuses verification.comparisons.line_row_problems, so it
    checks every column Section 5 checks - the three written here, but also
    the U.Price/VAT/Price the catalog record supplied - which puts the
    check at the point the state machine's own docstring always said it
    belonged: immediately after entry, on the line just entered, instead of
    at final verification with the order already saved.

    A retry cannot undo a stray value the previous attempt typed somewhere
    else; it re-locates and rewrites the target row only. The final
    verify_order_saved read-back is what catches collateral damage to
    another row.
    """
    values = {
        config.ORDER_LINE_GRID_SKU_COLUMN: item.sku,
        "Qty.": str(item.quantity),
        "Discount": str(item.discount),
    }
    problems: list[str] = []
    for _attempt in range(attempts):
        grid_pane, geometry = _measure_items_grid(
            main_window, items_label, settle_seconds=settle_seconds
        )
        row_bounds = grid_pane.rectangle()

        for column in config.ORDER_LINE_GRID_FILL_COLUMNS:
            cx, cy = geometry.cell_center(
                config.ORDER_LINE_GRID_COLUMNS.index(column), position - 1
            )
            point = (row_bounds.left + cx, row_bounds.top + cy)
            _fill_grid_text_cell(main_window, point, values[column], column=column)
        time.sleep(settle_seconds)

        problems = _line_row_problems(main_window, items_label, item, client=client)
        if not problems:
            return

    raise ManualReviewRequired(
        _ADD_LINES_STEP,
        f"line {position} ('{item.sku}') still wrong after {attempts} fill attempt(s): " + "; ".join(problems),
    )


def _measure_items_grid(
    main_window: Any,
    items_label: Any,
    *,
    settle_seconds: float,
    attempts: int = config.GRID_MEASURE_ATTEMPTS,
) -> tuple[Any, grid_geometry.GridGeometry]:
    """Screenshot the Items grid and measure its column/row geometry,
    re-capturing on a frame that doesn't measure cleanly.

    Two separate things can make one capture unusable, and both are
    transient. The window may not be in front - the capture is a
    screen-region grab, so an occluded window is photographed as whatever
    is on top of it (live, a grid capture came back showing this project's
    own editor). And the grid may be mid-relayout, right after the product
    picker closes - live, that measured as 8 columns of a 10-column grid
    and stopped an order whose first line was already perfect.

    Re-reading is safe in a way re-writing is not: this only measures, so
    the fail-closed rule is served by still raising once the attempts are
    spent, not by refusing to look twice.
    """
    last_error: ManualReviewRequired | None = None
    for attempt in range(attempts):
        controls.focus_foreground(main_window)
        controls.move_pointer_away(main_window)
        grid_pane = readback.items_grid_pane(main_window, items_label=items_label)
        try:
            geometry = grid_geometry.read_grid_geometry(
                vision_grounding.capture_control_image(grid_pane),
                expected_columns=len(config.ORDER_LINE_GRID_COLUMNS),
                step=_ADD_LINES_STEP,
            )
        except ManualReviewRequired as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(settle_seconds)
            continue
        return grid_pane, geometry
    assert last_error is not None
    raise last_error


def _line_row_problems(
    main_window: Any, items_label: Any, item: NormalizedLineItem, *, client: Any
) -> list[str]:
    """Read the Items grid back and compare the row for item.sku against
    the line item, returning one message per discrepant column (or per
    row-identification problem).

    Exact-match on the Item No. column, zero-or-many being a problem in
    itself - the same shape entity_resolution.matching applies to every
    search result.
    """
    controls.focus_foreground(main_window)
    # The pointer is still on the last cell written, whose tooltip would
    # otherwise be drawn over the row about to be read back.
    controls.move_pointer_away(main_window)
    grid_pane = readback.items_grid_pane(main_window, items_label=items_label)
    rows = vision_grounding.read_grid_rows(
        vision_grounding.capture_control_image(grid_pane),
        columns=verification_config.ORDER_ITEMS_GRID_COLUMNS,
        client=client,
        step=_ADD_LINES_STEP,
    )
    matches = [
        row
        for row in rows
        if comparisons.text_equals(item.sku, row.get(config.ORDER_LINE_GRID_SKU_COLUMN, ""))
    ]
    if len(matches) != 1:
        return [
            f"{len(matches)} row(s) in the Items grid have Item No. '{item.sku}' after adding it "
            f"(expected exactly one, out of {len(rows)} row(s) read)"
        ]
    return comparisons.line_row_problems(item, matches[0])


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


def _dialog_still_exists(dialog: Any) -> bool:
    """dialog.exists(), but treating a COMError as "gone" rather than
    propagating it.

    Confirmed live: once the underlying OS window is actually destroyed,
    re-resolving this handle-based wrapper's element can raise a raw
    _ctypes.COMError ("An event was unable to invoke any of the
    subscribers") instead of exists() returning False - the same class of
    transient UIA/COM hiccup controls.find_control already treats as "not
    there" rather than a hard failure.
    """
    from _ctypes import COMError

    try:
        return dialog.exists()
    except COMError:
        return False


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

    if not _dialog_still_exists(dialog):
        # Fakturama can auto-confirm and close this dialog on its own once
        # the typed search narrows to exactly one row - confirmed live,
        # repeatedly: searching an exact SKU that matches a single catalog
        # product closes the dialog immediately, with that row already
        # added, no row-click or OK needed. Treating the vanished dialog as
        # a failure here (the previous behavior) made the caller's retry
        # loop reopen the picker and add the same row again - once per
        # retry, since each retry hit this same auto-confirm and "failed"
        # the same way. Returning success here is what stops that.
        return
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


def _fill_grid_text_cell(main_window: Any, point: tuple[int, int], value: str, *, column: str = "?") -> None:
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

    A failure to type at all is converted to ManualReviewRequired naming
    the column, rather than escaping as a raw pywinauto error the state
    machine doesn't catch: some of this grid's cells open their own modal
    popup editor when clicked (Description's "position description" window
    - hit live when a mislocated click landed there), and a modal disables
    the main window, so the very next keystroke raises instead of going
    anywhere.
    """
    controls.focus(main_window)
    main_window.click_input(coords=point, absolute=True)
    try:
        main_window.type_keys("^a{DELETE}")
        main_window.type_keys(controls.escape_send_keys(value), with_spaces=True)
        main_window.type_keys("{TAB}")
    except ManualReviewRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - pywinauto ElementNotEnabled and friends
        raise ManualReviewRequired(
            _ADD_LINES_STEP,
            f"could not type {value!r} into the {column} cell at {point}: {type(exc).__name__} - "
            "the main window was not accepting input (a modal popup editor may have opened)",
        ) from exc


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
    _click_save(main_window)


def _click_save(main_window: Any) -> None:
    """Click the main toolbar's shared Save button.

    It saves whichever editor is currently active, so every caller is
    responsible for that editor being the active tab before calling -
    which is the whole difference between save_order and save_invoice.
    """
    controls.find_control(main_window, "Button", name=entity_config.SAVE_BUTTON_TITLE).click_input()


def save_invoice(app: Any, invoice_window: Any) -> None:
    """Re-activate the Invoice editor and save it.

    Unlike save_order, this cannot just click Save: the toolbar button
    acts on whichever editor is active, and by the time this runs the
    Order editor is also open and verify_payment_applied has been reading
    controls in between. `_reactivate_editor` is the established way to
    make an editor's own content current again (and to prove it worked
    rather than assume it) - probing for the Invoice's Cust.Ref. field,
    which is unambiguous here because Eclipse only exposes the *active*
    tab's contents to UI Automation, so the Order editor's identically
    named field is not visible while the Invoice is active.

    Saving is what actually creates the Invoice row: confirmed live that
    payment applied to an unsaved editor never reached the database at
    all, so this is a real state, not a formality.
    """
    main_window = app.main_window()
    _reactivate_editor(main_window, invoice_window, probe_name=verification_config.INVOICE_CUST_REF_EDIT_NAME)
    _click_save(main_window)


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
    written with controls.replace_text - real keystrokes, but clearing
    first: Fakturama pre-fills Value with the invoice total, so typing the
    total into it without clearing concatenated the two (a 678.30 invoice
    read back as 678,678.30, live).
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
        controls.replace_text(date_edit, order.payment_date.isoformat())

    _, _, gross_total = comparisons.order_level_totals(order)
    value_edit = controls.find_control(invoice_window, "Edit", name=verification_config.INVOICE_PAYMENT_VALUE_EDIT_NAME)
    controls.replace_text(value_edit, str(gross_total))
