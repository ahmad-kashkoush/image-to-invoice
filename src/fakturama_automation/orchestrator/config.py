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

# Cells filled in by hand after the pick. Qty./Discount because the catalog
# record has no per-order quantity or discount; Item No. because the picked
# row does not reliably carry the product's SKU: confirmed live, a line
# added from a product created in that same run showed "10" there (an
# internal record number) while the product's own Item Number field, and
# the Products list, both correctly read "CHR-ERG-01". An order built from
# pre-existing products showed the SKU. Rather than depend on which of
# those Fakturama does, the SKU is written explicitly - and then verified,
# like every other cell.
ORDER_LINE_GRID_FILL_COLUMNS = ["Item No.", "Qty.", "Discount"]
ORDER_LINE_GRID_SKU_COLUMN = "Item No."

# The row to fill is the line's own 1-based position, which the state
# machine knows because it adds lines in order - not whichever row
# Fakturama happens to be highlighting, and not a cell whose content is
# what's in question. ORDER_LINE_FILL_ATTEMPTS re-measures the grid from a
# fresh screenshot and retries if the read-back afterwards disagrees.
# Every column the Items grid physically draws, left to right - including
# the ones nothing reads ("Pos.", "Picture"), because cells are located by
# counting columns off the grid's own separator lines
# (ui_automation.grid_geometry), so the list has to match the rendering
# exactly, not just name the interesting columns. Distinct from
# verification.config.ORDER_ITEMS_GRID_COLUMNS, which is the subset read
# back by the vision grid read.
ORDER_LINE_GRID_COLUMNS = [
    "Pos.",
    "Qty.",
    "Item No.",
    "Picture",
    "Name",
    "Description",
    "VAT",
    "U.Price",
    "Discount",
    "Price",
]
ORDER_LINE_FILL_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_LINE_FILL_ATTEMPTS", "2"))

# Measuring the grid is a read, so a bad frame is retried rather than
# failed on: capturing right after the product picker closes can catch the
# grid mid-relayout, which measured as 8 columns of a 10-column grid on a
# live run and stopped an otherwise-correct order. Re-capturing a moment
# later read it correctly. A grid that is genuinely clipped still fails
# closed after these attempts.
GRID_MEASURE_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_GRID_MEASURE_ATTEMPTS", "3"))

# Re-selecting the Order tab after entity resolution navigated away can
# silently not take, leaving the editor's own fields unexposed to UIA - see
# actions._reactivate_editor.
EDITOR_ACTIVATE_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_EDITOR_ACTIVATE_ATTEMPTS", "3"))

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
