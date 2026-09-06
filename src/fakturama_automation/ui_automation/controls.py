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
    # Ambiguity is raised immediately, without waiting out the timeout: it
    # reflects the current parent/context, not a timing race.
    #
    # A transient COMError from descendants() is treated as "no match yet" and
    # retried - a genuine UIA hiccup, most often when querying a dialog moments
    # after connecting to its handle. Imported locally: Windows only.
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


def reactivate_editor(
    main_window: Any,
    editor: Any,
    *,
    probe_type: str,
    probe_name: str,
    attempts: int = 3,
    timeout_seconds: float = 5.0,
) -> Any:
    # Eclipse stops exposing a tab's content to UIA once you navigate away, and
    # this app navigates away constantly. set_focus() brings it back but can
    # silently not take, after which the next lookup fails as if the editor
    # were gone - so it is retried until a control that only exists inside this
    # editor is findable. Retrying is safe: selecting a tab changes nothing.
    #
    # Uses the held Pane reference, not a fresh find_control by title: that
    # breaks with AmbiguousControlError as soon as two same-titled tabs are
    # open, e.g. a prior run's never-saved draft. The probe control is returned
    # because re-finding it would race the activation this just proved.
    last_error: ControlNotFoundError | None = None
    for _attempt in range(attempts):
        focus(main_window)
        editor.set_focus()
        try:
            return find_control(
                main_window, probe_type, name=probe_name, timeout_seconds=timeout_seconds
            )
        except ControlNotFoundError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def window_still_exists(window: Any) -> bool:
    # Re-resolving a destroyed window's element can raise a raw COMError
    # instead of returning False.
    from _ctypes import COMError

    try:
        return window.exists()
    except COMError:
        return False


def focus(main_window: Any) -> None:
    # click_input() sends a real OS-level click at screen coordinates, so it
    # depends on main_window actually being foreground: without this, a
    # "successful" click landed on another app entirely. Call before every
    # click_input(), not once per screen - foreground can drift away.
    main_window.set_focus()


def focus_foreground(
    window: Any, timeout_seconds: float = 3.0, poll_interval_seconds: float = 0.2
) -> None:
    # focus() above asks and moves on - fine before a click_input(), which
    # fails loudly if it lands somewhere unexpected, but not before a
    # screenshot: capture_as_image() grabs the control's screen rectangle, so
    # an occluded window is captured as whatever is drawn over it. Live, a grid
    # capture came back showing a code editor and measured as 8 columns for a
    # 10-column grid. Wrong pixels are indistinguishable downstream.
    #
    # Windows can refuse SetForegroundWindow outright when the calling process
    # is not itself foreground - exactly an automation script's situation -
    # hence the retry and the GetForegroundWindow check rather than trusting
    # set_focus(). Imported locally: win32gui is Windows-only.
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
    # Call before screenshotting. click_input() leaves the pointer where it
    # clicked, and Fakturama pops that control's tooltip - drawn *over* the
    # window, so it lands in the next screenshot. Live: after the product
    # picker closed, the pointer still rested on the Items toolbar icon, and
    # its tooltip covered the grid's leading columns, measuring 8 of 10.
    #
    # Parks at the bottom edge rather than off-window: tooltips render next to
    # the pointer, so anything appearing there is far below the grids, and the
    # pointer never leaves the application.
    from pywinauto import mouse

    rect = window.rectangle()
    mouse.move(coords=(rect.left + rect.width() // 2, rect.bottom - 20))
    time.sleep(settle_seconds)


def set_text(
    control: Any, text: str, timeout_seconds: float = 5.0, poll_interval_seconds: float = 0.25
) -> None:
    # Fakturama briefly disables a field's Edit right after an adjacent field
    # changes. is_enabled() does not predict it (reads True immediately before
    # a retry that still fails), so the actual set_text() call is retried
    # rather than gated on a pre-check.
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
    return "".join(f"{{{ch}}}" if ch in _SEND_KEYS_SPECIAL_CHARS else ch for ch in text)


def type_text(control: Any, text: str) -> None:
    # Real keystrokes instead of set_text()'s ValuePattern.SetValue, which on
    # some fields (the Debtor Company field) reads back correctly but silently
    # fails to persist through Save. Not a blanket replacement: use only where
    # a field is confirmed to need it.
    control.click_input()
    control.type_keys(escape_send_keys(text), with_spaces=True)


def replace_text(control: Any, text: str) -> None:
    # For any field Fakturama pre-fills. type_text() inserts at the caret, so
    # on a pre-filled field it concatenates instead of replacing: live, a
    # payment Value of 678.30 typed over a default of 678.30 became 678,678.30,
    # and the VAT rate Value stayed at its "0%" default no matter what was
    # typed. The trailing Tab is separate: some of these fields only commit
    # what was typed when focus leaves them.
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
    # `auto_id` is filtered in Python, not passed to descendants(): pywinauto's
    # uia backend has no such kwarg on that call (passing one raises TypeError).
    kwargs: dict[str, Any] = {"control_type": control_type}
    if name is not None:
        kwargs["title"] = name
    matches = parent.descendants(**kwargs)
    if auto_id is not None:
        matches = [control for control in matches if control.element_info.automation_id == auto_id]
    return matches
