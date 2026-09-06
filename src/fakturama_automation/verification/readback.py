"""Reading a control's current contents back out of the live UI.

Keeps the three verification modules from each re-deriving "how do I read a
field's current value". *Where* a control is belongs to
`ui_automation.locators`, since the write path needs the same answers.

No pywinauto import: only the documented `window_text()`, `get_value()`,
`get_toggle_state()` are called on whatever the caller passes in.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import controls, locators, vision_grounding
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError
from fakturama_automation.verification import config


def window_title(window: Any) -> str:
    """Read a window/editor pane's own title (its accessible Name), e.g.
    to detect that the New Order editor's tab changed from "New Order" to
    an assigned order number after a save.
    """
    return window.window_text()


def field_value(control: Any) -> str:
    """Read a field's current *value* - what the user sees typed in it -
    not its accessible name.

    Never `window_text()`: pywinauto's uia EditWrapper resolves it to
    rich_text, which falls back to the element's Name when there is no
    TextPattern. Fakturama's SWT edits have none, so `window_text()` on the
    Cust.Ref. edit returns "Cust.Ref." rather than the reference in it, and
    every comparison built on it compared a label against a value and could
    never pass.

    The ValuePattern carries the typed text, with legacy Value as a
    fallback. A control exposing neither raises rather than degrading to the
    name again: an unreadable field must stop the run, not quietly compare
    equal to nothing.
    """
    try:
        return str(control.get_value())
    except Exception:  # noqa: BLE001 - no ValuePattern (pywinauto NoPatternInterfaceError) or not an Edit wrapper
        pass
    try:
        # ComboBoxes carry their current setting as the selected item, not
        # a value - the Invoice's payment-method combo among them.
        return str(control.selected_text())
    except Exception:  # noqa: BLE001 - not a combo, or nothing selected
        pass
    try:
        value = control.legacy_properties().get("Value")
    except Exception:  # noqa: BLE001 - no LegacyIAccessible pattern either
        value = None
    if value is None:
        raise ControlNotFoundError(
            f"control {control.window_text()!r} exposes neither a ValuePattern nor a legacy Value - "
            "cannot read its contents"
        )
    return str(value)


def read_field_text(
    window: Any,
    *,
    control_type: str = "Edit",
    name: str | None = None,
    auto_id: str | None = None,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> str:
    """Locate one field under window and read its current value.

    A selector that does not match a real control fails closed here:
    controls.find_control raises ControlNotFoundError or
    AmbiguousControlError rather than this function returning a
    plausible-looking empty string.
    """
    control = controls.find_control(window, control_type, name=name, auto_id=auto_id, timeout_seconds=timeout_seconds)
    return field_value(control)


def read_toggle_state(
    window: Any,
    *,
    control_type: str = "CheckBox",
    name: str | None = None,
    auto_id: str | None = None,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> bool:
    """Locate a CheckBox-like control and read whether it is checked, via
    pywinauto's documented UIA TogglePattern wrapper (`get_toggle_state()`,
    returning 1 for the "on" state).
    """
    control = controls.find_control(window, control_type, name=name, auto_id=auto_id, timeout_seconds=timeout_seconds)
    return control.get_toggle_state() == 1


def read_grid(
    window: Any,
    *,
    columns: list[str],
    client: Any = None,
) -> list[dict[str, str]]:
    """Screenshot the Items grid under window and read its rows.

    Activates this editor's tab and confirms its window is actually in front
    first: the capture is a screen-region grab, so an occluded or background
    tab reads as whatever is drawn over it - a plausible-looking wrong grid
    (typically an empty one), never an error.
    """
    window.set_focus()
    top_level = window.top_level_parent()
    controls.focus_foreground(top_level)
    # And with the pointer parked clear of the grid: a tooltip left showing
    # by the last click is drawn over the window, so it lands in the
    # screenshot and hides whatever it covers.
    controls.move_pointer_away(top_level)
    grid_pane = locators.items_grid_pane(window)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=client)
