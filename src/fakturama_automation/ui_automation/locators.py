"""Structural lookups for Fakturama controls that have no usable name.

`screens.py` says what a control is called; this module finds the ones that
cannot be found that way at all - blank-named, session-unstable auto_id,
reachable only via a neighbour that does have a stable name.

Here rather than in `verification` because both directions need them: the
payment-method combo verification reads is the one the payment step sets.

No pywinauto import: only the documented `parent()`, `children()`,
`descendants()` are called on whatever the caller passes in.
"""

from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import controls, screens
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError


def search_label(parent: Any, *, timeout_seconds: float = 5.0) -> Any:
    """The "Search:" Text control on a list screen or picker dialog.

    Returned rather than resolved straight to the Edit: callers also
    navigate *from* it (see picker_grid_pane).
    """
    return controls.find_control(
        parent, "Text", name=screens.SEARCH_LABEL_NAME, timeout_seconds=timeout_seconds
    )


def search_edit(label: Any, *, timeout_seconds: float = 5.0) -> Any:
    """The search box: the Edit under the "Search:" label's parent Pane."""
    return controls.find_control(label.parent(), "Edit", timeout_seconds=timeout_seconds)


def picker_grid_pane(label: Any) -> Any:
    """A picker dialog's results grid Pane, three Panes up from its
    "Search:" label, whose second child is the grid body.

    Walked one hop at a time so a stale/half-torn-down UIA tree raises
    ControlNotFoundError rather than a bare AttributeError.
    """
    node = label
    for hop in range(3):
        node = node.parent()
        if node is None:
            raise ControlNotFoundError(
                f"picker grid Pane lookup broke {hop + 1} parent() hop(s) up from the Search label - "
                "likely a stale/half-torn-down UIA tree"
            )
    return node.children()[1]


def sibling_after(control: Any, *, offset: int = 1) -> Any:
    """The control `offset` positions after `control` among their shared
    parent's children.

    For a caller that already holds the anchor and should not re-find it.
    """
    siblings = control.parent().children()
    return siblings[siblings.index(control) + offset]


def sibling_after_label(window: Any, label_name: str, *, offset: int = 1, timeout_seconds: float = 5.0) -> Any:
    """The control `offset` positions after a named Text label.

    Reaches the Order's Debtor-attach Image (offset 1 after "Addresses"),
    the Items toolbar's product-picker Image (1 after "Items"), and the
    pricing-mode ComboBox (2 after "Date", whose siblings run
    [No. Edit, "Date" Text, Date-value Pane, this ComboBox]).
    """
    label = controls.find_control(window, "Text", name=label_name, timeout_seconds=timeout_seconds)
    return sibling_after(label, offset=offset)


def sibling_pane_after_label(window: Any, label_name: str) -> Any:
    """The Pane immediately following a named Text label - the layout every
    form row whose own Edits are blank-named uses.
    """
    return sibling_after_label(window, label_name)


def items_grid_pane(window: Any, *, items_label: Any = None) -> Any:
    """The Items section's custom-rendered grid Pane, in the Order or
    Invoice editor alike: the "Items" label's toolbar Pane's next sibling.

    `items_label` lets a caller that already holds that Text control skip
    re-finding it.
    """
    items_label = items_label or controls.find_control(
        window, "Text", name=screens.ORDER_ITEMS_LABEL_NAME
    )
    toolbar_pane = items_label.parent()
    siblings = toolbar_pane.parent().children()
    return siblings[siblings.index(toolbar_pane) + 1]


def payment_details_pane(window: Any) -> Any:
    """The Invoice's payment-details Pane: the "paid" checkbox's next
    sibling.

    Checking "paid" replaces this Pane's second child in place (Due Days/
    Pay Until when unchecked, the date + "Value" row once checked), so
    callers needing those fields must check "paid" first.
    """
    paid_checkbox = controls.find_control(
        window, "CheckBox", name=screens.INVOICE_PAID_CHECKBOX_NAME
    )
    siblings = paid_checkbox.parent().children()
    return siblings[siblings.index(paid_checkbox) + 1]


def payment_method_combo(window: Any) -> Any:
    """The Invoice's payment-method ComboBox - the payment-details Pane's
    first child, present whether or not "paid" is checked.
    """
    return payment_details_pane(window).children()[0]


def payment_date_edit(window: Any) -> Any:
    """The Invoice's payment-date Edit - only present once "paid" is
    checked: the "at" label's next sibling Pane holds it.
    """
    date_row_pane = payment_details_pane(window).children()[1]
    at_label = controls.find_control(
        date_row_pane, "Text", name=screens.INVOICE_PAYMENT_DATE_LABEL_NAME
    )
    row_siblings = date_row_pane.children()
    date_pane = row_siblings[row_siblings.index(at_label) + 1]
    return date_pane.children()[0]
