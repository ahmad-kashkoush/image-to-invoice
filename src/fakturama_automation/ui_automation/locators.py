from __future__ import annotations

from typing import Any

from fakturama_automation.ui_automation import controls, screens
from fakturama_automation.ui_automation.exceptions import ControlNotFoundError


def search_label(parent: Any, *, timeout_seconds: float = 5.0) -> Any:
    return controls.find_control(
        parent, "Text", name=screens.SEARCH_LABEL_NAME, timeout_seconds=timeout_seconds
    )


def search_edit(label: Any, *, timeout_seconds: float = 5.0) -> Any:
    return controls.find_control(label.parent(), "Edit", timeout_seconds=timeout_seconds)


def picker_grid_pane(label: Any) -> Any:
    node = label
    for hop in range(3):
        node = node.parent()
        if node is None:
            raise ControlNotFoundError(
                f"picker grid Pane lookup broke {hop + 1} parent() hop(s) up from the Search label - "
                "likely a stale/half-torn-down UIA tree"
            )
    return node.children()[1]


def documents_grid_pane(container: Any) -> Any:
    """The Documents grid itself, without the left document-type tree.

    Every other list screen is captured by its named Pane directly. This one
    cannot be: Pane 'Documents' also contains the Invoices/Orders tree, which
    a vision read transcribes as extra columns and which grid_columns' pixel
    measurement counts as separators. Structural, because every Pane on the
    way down is blank-named (probes/probe-15-documents-list.txt):

        Pane 'Documents' > Pane > [Tree, Pane > [title+search strip, GRID]]
    """
    node = container
    for index in (0, 1, 1):
        children = node.children()
        if len(children) <= index:
            raise ControlNotFoundError(
                f"Documents grid Pane lookup found {len(children)} child(ren) where "
                f"child {index} was expected - likely a stale/half-torn-down UIA tree"
            )
        node = children[index]
    return node


def sibling_after(control: Any, *, offset: int = 1) -> Any:
    siblings = control.parent().children()
    return siblings[siblings.index(control) + offset]


def sibling_after_label(window: Any, label_name: str, *, offset: int = 1, timeout_seconds: float = 5.0) -> Any:
    label = controls.find_control(window, "Text", name=label_name, timeout_seconds=timeout_seconds)
    return sibling_after(label, offset=offset)


def sibling_pane_after_label(window: Any, label_name: str) -> Any:
    return sibling_after_label(window, label_name)


def items_grid_pane(window: Any, *, items_label: Any = None) -> Any:
    items_label = items_label or controls.find_control(
        window, "Text", name=screens.ORDER_ITEMS_LABEL_NAME
    )
    toolbar_pane = items_label.parent()
    siblings = toolbar_pane.parent().children()
    return siblings[siblings.index(toolbar_pane) + 1]


def payment_details_pane(window: Any) -> Any:
    paid_checkbox = controls.find_control(
        window, "CheckBox", name=screens.INVOICE_PAID_CHECKBOX_NAME
    )
    siblings = paid_checkbox.parent().children()
    return siblings[siblings.index(paid_checkbox) + 1]


def payment_method_combo(window: Any) -> Any:
    return payment_details_pane(window).children()[0]


def payment_date_edit(window: Any) -> Any:
    date_row_pane = payment_details_pane(window).children()[1]
    at_label = controls.find_control(
        date_row_pane, "Text", name=screens.INVOICE_PAYMENT_DATE_LABEL_NAME
    )
    row_siblings = date_row_pane.children()
    date_pane = row_siblings[row_siblings.index(at_label) + 1]
    return date_pane.children()[0]
