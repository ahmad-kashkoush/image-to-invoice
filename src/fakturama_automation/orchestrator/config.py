"""Configuration for the orchestrator.

Holds only the action selectors this section introduces on top of what
entity_resolution/config.py and verification/config.py already pin -
actions.py imports those directly rather than re-declaring them here.

There is no Payment Method field on the Order screen at all (confirmed
live) - it's attached later, at the Invoice stage, by actions.apply_payment.
"""

from __future__ import annotations

import os

# -- timeouts / polling --------------------------------------------------

SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_TIMEOUT_SECONDS", "5.0"))

# How long a just-opened picker dialog must stay visible before it's
# trusted as actually open, and how many times to re-click if not (the
# "Select a product"/"Select the address" pickers can flash open and close
# within a fraction of a second of the toolbar click that opens them).
DIALOG_STABILIZE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_STABILIZE_SECONDS", "0.3"))
DIALOG_OPEN_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_OPEN_ATTEMPTS", "3"))

# -- Main toolbar -----------------------------------------------------------

NEW_ORDER_BUTTON_TITLE = "Create: New Order"

# -- Order editor: attaching a Debtor via the "Select the address" picker ---
# The customer field is a multi-line address Edit; you attach a Debtor by
# clicking a small blank-named Image just to its left (located structurally,
# as the Image immediately following the "Addresses" Text in their shared
# parent Pane), which opens a genuinely separate top-level window - not a
# combo-dropdown popup - see ui_automation.app.FakturamaApp.top_level_window_by_title.
ORDER_ADDRESSES_LABEL_NAME = "Addresses"

# Picker dialog title and the grid columns Fakturama renders. Read via
# ui_automation.vision_grounding (UIA-invisible grid, like every list grid
# in this app). ORDER_PICKER_OK_BUTTON_TITLE is shared with the "Select a
# product" picker below - both use "OK".
ORDER_SELECT_ADDRESS_DIALOG_TITLE = "Select the address"
ORDER_SELECT_ADDRESS_SEARCH_COLUMNS = ["No.", "First Name", "Name", "Company", "ZIP", "City"]
ORDER_PICKER_OK_BUTTON_TITLE = "OK"

# -- Order editor: adding a line to the Items grid ---------------------------
# The "Items" toolbar's first Image (blank-named, located structurally as
# the first Image sibling following the "Items" Text) opens the "Select a
# product" picker below - a separate top-level window, structurally
# identical to "Select the address", not the second ("add a blank row")
# Image next to it.
ORDER_ITEMS_LABEL_NAME = "Items"

# Picking a row and clicking OK inserts a line with Item No./Name/
# Description/Price/VAT already filled from the Product's own catalog
# record - chosen over a blank-row-plus-manual-typing approach, which hit
# three separate bugs (Name opens its own unprobed popup editor, the VAT
# dropdown cell didn't reliably take effect, vision-computed cell positions
# for two columns got confused on a second line) - see
# Doc/adr/0007-orchestrator.md.
ORDER_SELECT_PRODUCT_DIALOG_TITLE = "Select a product"
ORDER_SELECT_PRODUCT_SEARCH_COLUMNS = ["Item No.", "Name", "Description", "Stock", "Price"]

# Only Qty./Discount remain to fill after the pick (the catalog record has
# no per-order quantity/discount) - Fakturama visually highlights the
# newly-added row.
ORDER_LINE_GRID_QTY_DISCOUNT_COLUMNS = ["Qty.", "Discount"]

# -- Order editor: pricing mode ----------------------------------------------

# The Order defaults to "Gross" pricing (a blank-named ComboBox next to
# Date), which extracts VAT backward out of U.Price - wrong when the source
# data is net-priced (CLAUDE.md's convention). Switching to "Net" is
# required for correct totals. Located via the stable "Date" label: the
# combo is that Text's sibling two positions later in their shared parent
# Pane ([No. Edit, "Date" Text, Date-value Pane, this ComboBox]).
ORDER_DATE_LABEL_NAME = "Date"
ORDER_PRICING_MODE_NET_OPTION = "Net"

# -- Invoice creation ---------------------------------------------------------

# The saved Order's "Create a follow-up document" panel has an "Invoice"
# button directly (distinct from the main toolbar's "Create: New Invoice").
# Clicking it opens a new tab, auto-activated, titled "New Invoice" until
# saved - the same "New X" pattern as verification.config.ORDER_TAB_TITLE_UNSAVED.
INVOICE_FROM_ORDER_BUTTON_TITLE = "Invoice"
INVOICE_EDITOR_PANE_NAME = "New Invoice"
