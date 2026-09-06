"""Small shared UI read-back helpers used by every verification module.

Keeps order_verification.py/invoice_verification.py/payment_verification.py
from each re-deriving "how do I read a field's current text back".

No pywinauto import here: `window` is whatever duck-typed pywinauto object
the caller already holds, and only its documented methods (`window_text()`,
`get_toggle_state()`) are called on it - keeps this module importable on
macOS/Linux.
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


def items_grid_pane(window: Any, *, label_name: str = "Items", items_label: Any = None) -> Any:
    """Locate the Items section's own custom-rendered grid Pane, in the
    Order or Invoice editor alike.

    Blank-named with a session-unstable auto_id - the "Items" Text label
    and its toolbar are a Pane, and the grid canvas is that Pane's own next
    sibling under their shared parent. Same structure in both editors, so
    this one helper serves both.

    `items_label` lets a caller that already holds this Text control
    (orchestrator.actions.add_order_line) skip re-finding it here.
    """
    items_label = items_label or controls.find_control(window, "Text", name=label_name)
    toolbar_pane = items_label.parent()
    siblings = toolbar_pane.parent().children()
    return siblings[siblings.index(toolbar_pane) + 1]


def read_grid(
    window: Any,
    *,
    columns: list[str],
    client: Any = None,
    step: str = "verification.read_grid",
) -> list[dict[str, str]]:
    """Screenshot the Items grid under window and read its rows via
    ui_automation.vision_grounding - the same fallback
    entity_resolution.resolver.search_grid_exact uses for Fakturama's
    list/search results grids, reused here for the Order/Invoice editor's
    own item-row grid (also UIA-invisible - see Doc/adr/0003's
    Consequences section, which names this exact reuse).
    """
    grid_pane = items_grid_pane(window)
    image_bytes = vision_grounding.capture_control_image(grid_pane)
    return vision_grounding.read_grid_rows(image_bytes, columns=columns, client=client, step=step)


def payment_details_pane(window: Any, *, paid_checkbox_name: str = "paid") -> Any:
    """Locate the Invoice's payment-details Pane: the "paid" checkbox's
    own next sibling, which holds the payment-method combo and (once
    "paid" is checked) the payment-date/Value row.

    Checking "paid" replaces this Pane's second child in place (Due Days/
    Pay Until controls when unchecked, an "at" date field + "Value" edit
    once checked) - callers needing the date/Value fields must check
    "paid" first, the same order apply_payment uses.
    """
    paid_checkbox = controls.find_control(window, "CheckBox", name=paid_checkbox_name)
    siblings = paid_checkbox.parent().children()
    return siblings[siblings.index(paid_checkbox) + 1]


def payment_method_combo(window: Any, *, paid_checkbox_name: str = "paid") -> Any:
    """Locate the Invoice's payment-method ComboBox (blank-named, no
    stable auto_id) - the payment-details Pane's first child, present
    regardless of whether "paid" is checked.
    """
    return payment_details_pane(window, paid_checkbox_name=paid_checkbox_name).children()[0]


def payment_date_edit(window: Any, *, paid_checkbox_name: str = "paid", at_label_name: str = "at") -> Any:
    """Locate the Invoice's payment-date Edit (blank-named) - only present
    once "paid" is checked (see payment_details_pane's docstring): the
    "at" Text label's own next sibling Pane holds it, mirroring the
    sibling-Pane navigation debtor.py's ZIP/City fields already use.
    """
    date_row_pane = payment_details_pane(window, paid_checkbox_name=paid_checkbox_name).children()[1]
    at_label = controls.find_control(date_row_pane, "Text", name=at_label_name)
    row_siblings = date_row_pane.children()
    date_pane = row_siblings[row_siblings.index(at_label) + 1]
    return date_pane.children()[0]
