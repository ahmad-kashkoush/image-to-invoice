"""Configuration for the orchestrator.

Section 7 (orchestrator). Kept deliberately small and env-driven, mirroring
every other section's config.py. Holds only the action selectors this
section introduces on top of what entity_resolution/config.py
(APP_TITLE_RE, SAVE_BUTTON_TITLE) and verification/config.py (the Order
editor's named fields, ORDER_TAB_TITLE_UNSAVED) already pin - actions.py
imports those directly rather than re-declaring them here.

Probed and safe to pin now: the main toolbar's "Create: New Order" button
(probes/probe-00-root.txt).

Left as explicit empty-string `# TODO probe` placeholders, the same
fail-closed convention verification/config.py established (see its
docstring): no VM probe session has captured the Order's own customer/
payment-method attachment fields, the order-line grid's entry affordance
(as opposed to verification's read-only grid pane, already pinned there),
or the Data > Documents "create linked invoice" action and the resulting
Invoice editor's own pane. Against a real window these fail closed
(ControlNotFoundError/AmbiguousControlError) rather than guessing - see
Doc/adr/0007-orchestrator.md and TODo.md's "Not started" section.
"""

from __future__ import annotations

import os

# -- timeouts / polling --------------------------------------------------

SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_TIMEOUT_SECONDS", "5.0"))

# -- Main toolbar (probes/probe-00-root.txt) ------------------------------

NEW_ORDER_BUTTON_TITLE = "Create: New Order"

# -- Order editor write actions: no VM probe yet (fail closed) -----------

# The control that attaches an already-resolved Debtor/Payment Method
# identity to *this* Order - distinct from entity_resolution.debtor/
# payment_method's own search-then-create screens (fully probed) - has
# never been opened in a probe session. Control type is an unconfirmed
# guess (Edit/ComboBox); left as "Edit" pending a probe.
ORDER_CUSTOMER_FIELD_AUTO_ID = ""  # TODO probe
ORDER_PAYMENT_METHOD_FIELD_AUTO_ID = ""  # TODO probe

# The order-line grid itself is the same UIA-invisible custom-rendered
# canvas verification.config.ORDER_ITEMS_GRID_PANE_AUTO_ID reads from
# (reused for entry, not duplicated) - but entering a line into it needs
# whatever "add line" affordance Fakturama exposes (a button or keyboard
# shortcut), which no probe has captured yet.
ORDER_LINE_ADD_BUTTON_TITLE = ""  # TODO probe

# -- Invoice creation: no VM probe of Data > Documents or a linked -------
# -- Invoice editor exists yet (verification/config.py has the identical --
# -- gap for the Invoice editor's own fields). ---------------------------

INVOICE_FROM_ORDER_BUTTON_TITLE = ""  # TODO probe: Data > Documents "create linked invoice" action
INVOICE_EDITOR_PANE_NAME = ""  # TODO probe: the resulting linked Invoice editor's own pane
