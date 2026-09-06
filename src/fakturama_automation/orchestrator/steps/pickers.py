# Imports neither editor - it takes the button that opens the dialog and a
# callback for describing a wrong row count, so both callers share one
# implementation.

from __future__ import annotations

import time
from typing import Any, Callable

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.orchestrator import config
from fakturama_automation.ui_automation import controls, locators, screens, vision_grounding
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError, DialogTimeoutError


def pick_row_via_picker(
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
    # The dialog can vanish anywhere in the interaction, not just at open time
    # (identical back-to-back attempts, one failure and one success), so the
    # whole open-search-pick cycle is the retryable unit - and
    # _open_picker_dialog runs with attempts=1 so its own retry does not
    # multiply against this one. Escape closes any leftover dialog first, so
    # the next click cannot collide with a stale window of the same title.
    #
    # ManualReviewRequired - a real "zero or many rows" outcome, not a race -
    # propagates immediately rather than being retried.
    #
    # A retry can reopen a picker that already succeeded. That is safe only
    # because the caller then checks that exactly one row holds this key: the
    # retry is not assumed idempotent, it is proven to be.
    last_error: Exception = ControlNotFoundError(
        f"{dialog_title!r} was never opened: attempts={attempts}"
    )
    for _attempt in range(attempts):
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
    # Two distinct failures, both retried here. The dialog can flash open and
    # closed within a fraction of a second of the click, so its visibility is
    # re-checked after a stabilize delay. And window-visible is not
    # content-ready: it can pass that check with no "Search:" box rendered yet,
    # so its content is probed too.
    last_error: Exception = ControlNotFoundError(
        f"{dialog_title!r} was never opened: attempts={attempts}"
    )
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
            locators.search_label(dialog, timeout_seconds=stabilize_seconds)
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
    label = locators.search_label(dialog, timeout_seconds=timeout_seconds)
    locators.search_edit(label, timeout_seconds=timeout_seconds).set_text(key)
    time.sleep(settle_seconds)

    if not controls.window_still_exists(dialog):
        # Fakturama auto-confirms and closes this dialog once the search
        # narrows to exactly one row - the row is already added, nothing
        # left to click. Treating that as a failure made the caller's retry
        # loop reopen the picker and add the same row again, once per retry.
        return
    # Re-found fresh, not reused: typing rebuilds the dialog's widget tree
    # as it filters, breaking the earlier reference's .parent() chain.
    label = locators.search_label(dialog, timeout_seconds=timeout_seconds)
    grid_pane = locators.picker_grid_pane(label)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    rows = vision_grounding.read_grid_rows_located(image_bytes, columns=columns, client=client)
    if len(rows) != 1:
        raise ManualReviewRequired(step, not_one_row_reason(len(rows), rows))

    bounds = grid_pane.rectangle()
    x, y, width, height = rows[0].bbox
    screen_point = (bounds.left + x + width // 2, bounds.top + y + height // 2)
    # Fresh focus before each click: the vision read above is a real network
    # call, long enough for foreground focus to drift away from Fakturama.
    controls.focus(dialog)
    dialog.click_input(coords=screen_point, absolute=True)
    controls.focus(dialog)
    controls.find_control(dialog, "Button", name=screens.PICKER_OK_BUTTON_TITLE).click_input()
