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
