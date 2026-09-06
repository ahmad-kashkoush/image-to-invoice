"""Control location helpers built on pywinauto's uia backend.

Locate controls by control type, accessible name or label, UI hierarchy
and container, and relationships to surrounding controls. Never by screen
coordinates.

No pywinauto import here: `parent` is whatever pywinauto object the caller
already holds, and only its documented `descendants()` method is used -
keeps this module (and its tests) importable on macOS/Linux.

Uses `parent.descendants()` (TreeScope_Descendants), not `.children()`
(immediate children only): callers pass `main_window` as `parent` for
controls several Panes/Toolbars deep. `auto_id` is an optional filter
alongside `control_type`/`name` for controls with no accessible name at
all (common on Fakturama's Debtor/Product/Payment screens).
"""

from __future__ import annotations

import time
from typing import Any

from fakturama_automation.ui_automation import waits
from fakturama_automation.ui_automation.exceptions import (
    AmbiguousControlError,
    ControlNotFoundError,
    WindowFocusError,
)


def find_control(
    parent: Any,
    control_type: str,
    name: str | None = None,
    auto_id: str | None = None,
    timeout_seconds: float = 5.0,
) -> Any:
    """Locate a single control under parent, retrying within timeout_seconds.

    Ambiguity (more than one match) is raised immediately, without waiting
    out the timeout: it reflects the current parent/context, not a timing
    race, so resolving it means passing a more specific parent, not retrying.

    A transient `_ctypes.COMError` from `parent.descendants()` is treated
    as "no match yet" and retried rather than raised - confirmed live this
    is a genuine transient UIA hiccup, most often seen querying a dialog
    moments after connecting to its window handle. Imported locally since
    it only exists on Windows.
    """
    from _ctypes import COMError

    matches: list[Any] = []

    def _has_any_match() -> bool:
        nonlocal matches
        try:
            matches = find_all_controls(parent, control_type, name, auto_id)
        except COMError:
            matches = []
            return False
        return len(matches) >= 1

    if not waits.wait_until(_has_any_match, timeout_seconds=timeout_seconds):
        raise ControlNotFoundError(
            f"no {control_type} control named {name!r} (auto_id={auto_id!r}) found within {timeout_seconds}s"
        )
    if len(matches) > 1:
        raise AmbiguousControlError(
            f"{len(matches)} {control_type} controls named {name!r} (auto_id={auto_id!r}) matched; "
            "expected exactly one"
        )
    return matches[0]


def focus(main_window: Any) -> None:
    """Bring main_window to the OS foreground immediately before a
    click_input() call.

    click_input() sends a real OS-level mouse click at screen coordinates,
    so it depends on main_window being the actual foreground window.
    Confirmed live: without this, a "successful" click on another app's
    foreground window landed nowhere near Fakturama. Call before every
    click_input(), not just once per screen - later actions can lose
    foreground to another application.
    """
    main_window.set_focus()


def focus_foreground(
    window: Any, timeout_seconds: float = 3.0, poll_interval_seconds: float = 0.2
) -> None:
    """Bring window to the OS foreground and confirm it actually got there,
    retrying within timeout_seconds and raising WindowFocusError if not.

    `focus()` above asks and moves on. That's fine before a click_input(),
    which fails loudly if it lands somewhere unexpected, but not before a
    screenshot: capture_as_image() grabs the control's screen rectangle, so
    an occluded window is captured as whatever is drawn on top of it. That
    is not a hypothetical - a grid capture during a live run came back
    showing the editor this project is being written in, and the geometry
    read of it reported "8 columns" for a 10-column grid. Wrong pixels are
    indistinguishable from right ones downstream, so this confirms rather
    than assumes.

    Windows can refuse SetForegroundWindow outright when the calling
    process isn't itself in the foreground, which is exactly the situation
    an automation script runs in - hence retrying, and hence checking
    GetForegroundWindow rather than trusting set_focus() to have worked.
    Imported locally: win32gui only exists on Windows, and this module is
    imported cross-platform.
    """
    import win32gui

    deadline = time.monotonic() + timeout_seconds
    handle = window.element_info.handle
    while True:
        try:
            window.set_focus()
        except Exception:  # noqa: BLE001 - a refused activation is retried, not raised
            pass
        if win32gui.GetForegroundWindow() == handle:
            return
        if time.monotonic() >= deadline:
            foreground = win32gui.GetForegroundWindow()
            raise WindowFocusError(
                f"could not bring window {window.window_text()!r} (handle {handle}) to the "
                f"foreground within {timeout_seconds}s - {win32gui.GetWindowText(foreground)!r} "
                "is in front of it; a screenshot now would capture that window instead"
            )
        time.sleep(poll_interval_seconds)


def move_pointer_away(window: Any, settle_seconds: float = 0.4) -> None:
    """Park the mouse pointer at the bottom of window and wait for any
    tooltip it was showing to disappear. Call before screenshotting.

    click_input() leaves the pointer wherever it clicked, and Fakturama
    then pops that control's tooltip - which is drawn *over* the window,
    so it lands in any screenshot taken next. Confirmed live: after the
    "Select a product" picker closes, the pointer is still resting on the
    Items toolbar icon that opened it, and the resulting tooltip covered
    the item grid's leading columns, which measured as an 8-column grid
    where there are 10.

    Parks at the bottom edge rather than off-window: tooltips render next
    to the pointer, so anything that does appear there is far below the
    editor's grids instead of on top of them, and the pointer never leaves
    the application.
    """
    from pywinauto import mouse

    rect = window.rectangle()
    mouse.move(coords=(rect.left + rect.width() // 2, rect.bottom - 20))
    time.sleep(settle_seconds)


def set_text(
    control: Any, text: str, timeout_seconds: float = 5.0, poll_interval_seconds: float = 0.25
) -> None:
    """set_text() on control, retrying while it raises a transient "element
    not enabled" COM error.

    Fakturama can briefly disable a field's Edit right after an adjacent
    field changes. `is_enabled()` is not a reliable predictor of this
    (confirmed live: reads True immediately before a retry that still
    fails), so this retries the actual `set_text()` call on that specific
    error rather than gating on a pre-check.
    """
    from _ctypes import COMError

    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            control.set_text(text)
            return
        except COMError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(poll_interval_seconds)


_SEND_KEYS_SPECIAL_CHARS = "+^%~(){}"


def escape_send_keys(text: str) -> str:
    """Escape pywinauto send_keys' special/modifier characters (+^%~(){})
    so type_keys sends text literally. Shared by type_text and any other
    caller driving type_keys directly.
    """
    return "".join(f"{{{ch}}}" if ch in _SEND_KEYS_SPECIAL_CHARS else ch for ch in text)


def type_text(control: Any, text: str) -> None:
    """Type text into control via real keystrokes (type_keys), instead of
    set_text()'s UIA ValuePattern.SetValue.

    Needed for entity_resolution.debtor's Company field: set_text() reads
    back correctly but silently fails to persist through Save (confirmed
    live) - real keystrokes fix it. Not a blanket replacement for
    set_text(); use only where a field is confirmed to need it.
    """
    control.click_input()
    control.type_keys(escape_send_keys(text), with_spaces=True)


def replace_text(control: Any, text: str) -> None:
    """Click into control, clear what it already holds, type text, and
    commit with a trailing Tab.

    For any field Fakturama pre-fills. type_text() above inserts at the
    caret, so on a pre-filled field it concatenates instead of replacing -
    live, that turned a payment Value of 678.30 typed over a default of
    678.30 into 678,678.30, and (in the VAT rate form) left Value stuck at
    its "0%" default no matter what was typed, which then broke that
    record's own lookup on the next run. The trailing Tab matters
    separately: some of these fields only commit what was typed when focus
    leaves them.
    """
    control.click_input()
    control.type_keys("^a{DELETE}")
    control.type_keys(escape_send_keys(text), with_spaces=True)
    control.type_keys("{TAB}")


def find_all_controls(
    parent: Any,
    control_type: str,
    name: str | None = None,
    auto_id: str | None = None,
) -> list[Any]:
    """Locate every matching control under parent, no retry.

    `auto_id` is filtered here in Python, not passed to `descendants()`:
    pywinauto's uia backend has no `auto_id`/`automation_id` kwarg on that
    call (confirmed: passing one raises TypeError).
    """
    kwargs: dict[str, Any] = {"control_type": control_type}
    if name is not None:
        kwargs["title"] = name
    matches = parent.descendants(**kwargs)
    if auto_id is not None:
        matches = [control for control in matches if control.element_info.automation_id == auto_id]
    return matches
