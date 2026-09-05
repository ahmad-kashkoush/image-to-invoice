"""Small shared UI read-back helpers used by every verification module.

Section 5 (verification). Keeps order_verification.py/
invoice_verification.py/payment_verification.py from each re-deriving
"how do I read a field's current text back" and gives their tests one
seam to fake, the same role entity_resolution.resolver plays for the
search-then-create half of Section 4.

No pywinauto import here: `window` is whatever duck-typed pywinauto
object (a UIAWrapper) the caller already holds, and only its documented
methods (`window_text()`, `get_toggle_state()`) are called on it -
the same seam ui_automation.controls/waits and
ui_automation.vision_grounding already use (Doc/adr/0002). This keeps
this module (and its tests) importable and unit-testable on macOS/Linux.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import controls, vision_grounding
from fakturama_automation.verification import config


def window_title(window: Any) -> str:
    """Read a window/editor pane's own title (its accessible Name), e.g.
    to detect that the New Order editor's tab changed from "New Order" to
    an assigned order number after a save.
    """
    return window.window_text()


def read_field_text(
    window: Any,
    *,
    control_type: str = "Edit",
    name: str | None = None,
    auto_id: str | None = None,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
) -> str:
    """Locate one field under window and read its current text.

    A placeholder selector (name/auto_id == "", for a control not yet
    pinned by a VM probe - see verification/config.py) fails closed here:
    controls.find_control raises ControlNotFoundError or
    AmbiguousControlError rather than this function returning a
    plausible-looking empty string.
    """
    control = controls.find_control(window, control_type, name=name, auto_id=auto_id, timeout_seconds=timeout_seconds)
    return control.window_text()


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
    pane_auto_id: str,
    columns: list[str],
    client: Any = None,
    timeout_seconds: float = config.DIALOG_TIMEOUT_SECONDS,
    step: str = "verification.read_grid",
) -> list[dict[str, str]]:
    """Screenshot a custom-rendered (UIA-invisible) grid pane under window
    and read its rows via ui_automation.vision_grounding - the same
    fallback entity_resolution.resolver.search_grid_exact uses for
    Fakturama's list/search results grids, reused here for the Order/
    Invoice editor's own item-row grid (also UIA-invisible - see
    Doc/adr/0003's Consequences section, which names this exact reuse).
    """
    grid_pane = controls.find_control(window, "Pane", auto_id=pane_auto_id, timeout_seconds=timeout_seconds)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=client, step=step)
