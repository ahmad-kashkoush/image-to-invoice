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
from fakturama_automation.ui_automation.exceptions import AmbiguousControlError, ControlNotFoundError


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
