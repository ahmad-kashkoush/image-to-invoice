"""Configuration for verification.

Section 5 (verification). Mirrors entity_resolution/config.py's pattern:
env-driven timeouts plus every control identifier this section needs,
kept in one file so a future re-probe only touches this file.

Order/Invoice editor fields are pinned by NAME here, unlike
entity_resolution/config.py's Debtor/Product/VAT/Payment selectors, which
are pinned by auto_id. Comparing probes/probe-01-create-order.txt (empty
New Order editor) against probes/probe-02-fill-create-order.txt (the same
editor, filled) - two separate app launches - shows every numeric auto_id
in the editor's field tree changes between sessions (e.g. the Cust.Ref.
Edit is auto_id="132674" in one capture and auto_id="198488" in the
other), while each field's accessible name/title ("Cust.Ref.",
"Total Gross", "Discount", "VAT", "Total") stays identical in both. So
unlike the Debtor/Product/VAT/Payment forms (session-stable enough that
Section 4 pinned their auto_ids), the Order/Invoice editor's named fields
are looked up by name here - this is also just Doc/Design.md's own stated
priority order (accessible name first, auto_id only as a fallback for
controls that have none - see ui_automation/controls.py's docstring for
the mirror case in Section 4).

Several selectors below have no VM probe at all yet: no probe session has
opened Data > Documents, the linked Invoice editor, or an Invoice's
payment controls (paid checkbox/payment date/Value) - only the payment
*method* "Term of Payment" form was probed
(probes/probe-10-payment-create-form.txt). These are left as explicit
empty-string placeholders with a `# TODO probe` comment rather than a
guess, so a lookup against a real window fails closed (raises
ControlNotFoundError/AmbiguousControlError) instead of silently matching
the wrong control. See Doc/adr/0004-verification.md.
"""

from __future__ import annotations

import os

# -- timeouts -------------------------------------------------------------

VERIFY_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_VERIFICATION_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_VERIFICATION_DIALOG_TIMEOUT_SECONDS", "5.0"))

# -- Order editor (probes/probe-01-create-order.txt, probe-02-fill-create-order.txt) --
# The New Order editor's own tab/pane title is "New Order" until saved,
# at which point it becomes the assigned order number (confirmed: the
# same editor pane is titled "New Order" empty and "PO000001" filled in
# the two probe captures) - the persistence signal verify_order_saved
# checks first.
ORDER_TAB_TITLE_UNSAVED = "New Order"

ORDER_CUST_REF_EDIT_NAME = "Cust.Ref."

# Fakturama's own label for the field holding the sum of line net totals
# (Task Description's "Total Net") - confirmed as a real, named control,
# but its exact semantic role (is it really pre-VAT net, or something
# else) was not independently confirmed against a real filled+saved order;
# see Doc/adr/0004-verification.md.
ORDER_TOTAL_GROSS_EDIT_NAME = "Total Gross"
ORDER_DISCOUNT_EDIT_NAME = "Discount"
ORDER_VAT_EDIT_NAME = "VAT"
ORDER_TOTAL_EDIT_NAME = "Total"

# The order line-item grid is a custom-rendered (NatTable) canvas with no
# UIA children at all (consistent with ADR 0003's finding for entity
# resolution's list grids) - read via ui_automation.vision_grounding, like
# those. Its containing Pane's auto_id was captured
# (probes/probe-02-fill-create-order.txt: 'ItemsPane2'/'ItemsPane3') but,
# like every other auto_id in this editor, is not confirmed stable across
# sessions and has no accessible name to fall back on either.
ORDER_ITEMS_GRID_PANE_AUTO_ID = ""  # TODO probe: confirm a session-stable identifier

# Column labels per Task Description 3.13-3.16 (Qty., U.Price, VAT,
# Discount, Price) - not read from a probe (the grid itself is UIA-
# invisible, so there is nothing to probe for column headers); confirm
# against a real screenshot once ORDER_ITEMS_GRID_PANE_AUTO_ID is probed.
ORDER_ITEMS_GRID_COLUMNS = ["SKU", "Qty.", "U.Price", "VAT", "Discount", "Price"]  # TODO confirm

# -- Invoice editor: created directly from the Order (Task 4.6-4.7), so --
# -- assumed to share the Order editor's layout; no dedicated VM probe ---
# -- of a linked Invoice editor exists yet. ------------------------------

INVOICE_CUST_REF_EDIT_NAME = "Cust.Ref."  # assumed same name as the Order editor's; unconfirmed
INVOICE_TOTAL_EDIT_NAME = "Total"  # assumed same name as the Order editor's; unconfirmed
INVOICE_ITEMS_GRID_PANE_AUTO_ID = ""  # TODO probe
INVOICE_ITEMS_GRID_COLUMNS = ORDER_ITEMS_GRID_COLUMNS

# -- Invoice payment fields: no VM probe exists (Task 5.2/5.3/5.6) -------

INVOICE_PAYMENT_METHOD_COMBO_NAME = ""  # TODO probe
INVOICE_PAID_CHECKBOX_NAME = ""  # TODO probe
INVOICE_PAYMENT_DATE_EDIT_NAME = ""  # TODO probe
INVOICE_PAYMENT_VALUE_EDIT_NAME = ""  # TODO probe
