from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import config, controls, locators, vision_grounding
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError


def window_title(window: Any) -> str:
    return window.window_text()


def field_value(control: Any) -> str:
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
    timeout_seconds: float = config.READ_TIMEOUT_SECONDS,
) -> str:
    control = controls.find_control(window, control_type, name=name, auto_id=auto_id, timeout_seconds=timeout_seconds)
    return field_value(control)


def read_toggle_state(
    window: Any,
    *,
    control_type: str = "CheckBox",
    name: str | None = None,
    auto_id: str | None = None,
    timeout_seconds: float = config.READ_TIMEOUT_SECONDS,
) -> bool:
    control = controls.find_control(window, control_type, name=name, auto_id=auto_id, timeout_seconds=timeout_seconds)
    return control.get_toggle_state() == 1


def read_items_grid(
    window: Any,
    *,
    columns: list[str],
    client: Any = None,
) -> list[dict[str, str]]:
    window.set_focus()
    top_level = window.top_level_parent()
    controls.focus_foreground(top_level)
    controls.move_pointer_away(top_level)
    grid_pane = locators.items_grid_pane(window)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=client)


def app_error_text(window: Any) -> str | None:
    """What Fakturama is currently complaining about, or None.

    Two surfaces, because this app uses both and neither is a top-level
    window:

    Fakturama renders its message boxes as child shells of the main window,
    not as top-level windows, so `app.top_level_window_by_title` - which
    enumerates top-level windows - cannot see them and nothing in the pipeline
    reported them. A modal also disables the controls underneath it, so the
    symptom is whatever the current step was doing: live on 2026-09-15,
    "No default value found for Shippings. Please set one from list!" surfaced
    as `no Pane control named 'New Order' found within 5.0s`, and cost twenty
    minutes of probing to find.

    Deliberately not matched by title: any modal is worth reporting, and the
    set of titles this app uses is not known.
    """
    return _modal_text(window) or _error_view_text(window)


def _modal_text(window: Any) -> str | None:
    try:
        dialogs = window.descendants(control_type="Window")
    except Exception:  # noqa: BLE001 - a torn-down window has nothing to report
        return None
    for dialog in dialogs:
        try:
            title = dialog.element_info.name or ""
            message = "; ".join(
                text.element_info.name
                for text in dialog.descendants(control_type="Text")
                if text.element_info.name
            )
        except Exception:  # noqa: BLE001 - the dialog closed while being read
            continue
        if message:
            return f"{title or 'dialog'}: {message}"
        if title:
            return title
    return None


def _error_view_text(window: Any) -> str | None:
    # The second surface: Eclipse's own "Error" view, which opens as an editor
    # tab rather than a dialog, so nothing above finds it. Live on 2026-09-15
    # a clean-profile run stopped with `no Edit control named 'Cust.Ref.'`
    # while this view was holding the actual cause - "Unable to create class
    # 'com.sebulli.fakturama.parts.DocumentEditor'". The message sits in an
    # unnamed read-only Edit, reachable only through the legacy value.
    try:
        tabs = window.descendants(control_type="TabItem")
        if not any((tab.element_info.name or "") == "Error" for tab in tabs):
            return None
        for edit in window.descendants(control_type="Edit"):
            if edit.element_info.name:
                continue
            value = str(edit.legacy_properties().get("Value") or "").strip()
            if value:
                return f"Error view: {value}"
    except Exception:  # noqa: BLE001 - diagnostics never replace the real failure
        return None
    return None
