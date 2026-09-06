"""The UI write actions the state machine composes, one module per screen.

Kept out of state_machine.py so the state loop reads as control flow, not UI
mechanics. The loop calls the names below; the screen modules keep their own
private helpers out of its view.
"""

from __future__ import annotations

from fakturama_automation.orchestrator.steps.invoice_editor import (
    apply_payment,
    create_linked_invoice,
    save_invoice,
)
from fakturama_automation.orchestrator.steps.order_editor import (
    add_order_line,
    open_new_order,
    populate_order_fields,
    save_order,
)

__all__ = [
    "add_order_line",
    "apply_payment",
    "create_linked_invoice",
    "open_new_order",
    "populate_order_fields",
    "save_invoice",
    "save_order",
]
