"""Configuration for verification.

Order/Invoice editor fields are pinned by accessible NAME, not auto_id
(unlike entity_resolution/config.py's Debtor/Product/VAT/Payment
selectors): probing the same editor across two app launches showed every
field's numeric auto_id changes between sessions while its name/title
("Cust.Ref.", "Total Gross", etc.) stays identical.

The payment-method combo and payment-date edit on the Invoice have no
stable name or auto_id at all - readback.payment_method_combo/
payment_date_edit locate them structurally instead.
"""

from __future__ import annotations

import os

# -- timeouts -------------------------------------------------------------

VERIFY_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_VERIFICATION_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_VERIFICATION_DIALOG_TIMEOUT_SECONDS", "5.0"))

# -- Order editor ------------------------------------------------------------
# Tab/pane title is "New Order" until saved, then becomes the assigned order
# number - the persistence signal verify_order_saved checks first.
ORDER_TAB_TITLE_UNSAVED = "New Order"

ORDER_CUST_REF_EDIT_NAME = "Cust.Ref."

# Mode-dependent: reads "Total Gross" in the Order's default Gross pricing
# mode, "Total Net" once switched to Net. Pinned to Net (this codebase's
# convention throughout, CLAUDE.md) so a Gross-mode order fails closed
# instead of silently matching the wrong field.
ORDER_TOTAL_NET_EDIT_NAME = "Total Net"
ORDER_DISCOUNT_EDIT_NAME = "Discount"
ORDER_VAT_EDIT_NAME = "VAT"
ORDER_TOTAL_EDIT_NAME = "Total"

# Matches the grid's own visible headers; comparisons.line_row_problems
# reads these same keys back out.
ORDER_ITEMS_GRID_COLUMNS = ["Item No.", "Qty.", "U.Price", "VAT", "Discount", "Price"]

# -- Invoice editor -----------------------------------------------------------
# Created directly from the Order; shares its layout and inherited pricing mode.

INVOICE_CUST_REF_EDIT_NAME = "Cust.Ref."
INVOICE_TOTAL_EDIT_NAME = "Total"
INVOICE_ITEMS_GRID_COLUMNS = ORDER_ITEMS_GRID_COLUMNS

# -- Invoice payment fields ---------------------------------------------------
# Only these two have a stable accessible name; the payment-method combo and
# payment-date edit are blank-named and located structurally instead, via
# readback.payment_method_combo/payment_date_edit.

INVOICE_PAID_CHECKBOX_NAME = "paid"
INVOICE_PAYMENT_VALUE_EDIT_NAME = "Value"
