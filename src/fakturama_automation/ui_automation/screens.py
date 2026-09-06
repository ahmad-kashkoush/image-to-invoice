"""Every Fakturama control identifier this codebase uses, by screen.

A selector describes a screen, not whichever section needed it first, and
the write path and the read-back path need identical answers. This module
imports nothing, so any layer may read it. Timeouts and retry counts are
not here - those are per-section tunables and live in each package's own
`config.py`.

Every identifier is pinned from a live VM probe (`probes/probe-*.txt`) or a
live session recorded in `Doc/implementation-notes.md`. Nothing is guessed;
a re-probe should only ever touch this file. A few entries have no caller
yet and are kept as probe inventory.
"""

from __future__ import annotations

# -- Application -------------------------------------------------------------

# Prefix match: the title's path suffix is environment-specific.
APP_TITLE_RE = r"^Fakturama - "

# -- Shared across every screen ----------------------------------------------

# No auto_id anywhere it appears. Saves whichever editor is active, so the
# caller owns making that the right one.
SAVE_BUTTON_TITLE = "Save the current contents"

# Labels the search box on every list screen and picker dialog; the Edit
# itself is blank-named and found as this label's sibling.
SEARCH_LABEL_NAME = "Search:"

# Always this auto_id whichever list is active, while its *title* changes -
# so never disambiguate by it alone; select the nav item first.
LIST_EDITOR_TAB_AUTO_ID = "525638"

# -- Navigation View: the entity list screens --------------------------------
# Nav items render as Text, not Button, so they are clicked by rect. Each
# results grid has a stable accessible name (its auto_id is not stable),
# which doubles as proof the intended list is actually on screen. The rows
# are UIA-invisible, so the columns below name what the vision read should
# extract, not UIA properties.

DEBTORS_NAV_NAME = "Debtors"
DEBTORS_GRID_PANE_NAME = "Debtors"
DEBTORS_SEARCH_COLUMNS = ["Company Name"]

PRODUCTS_NAV_NAME = "Products"
PRODUCTS_GRID_PANE_NAME = "Products"
PRODUCTS_SEARCH_COLUMNS = ["Item Number"]

# Fakturama's nav says "VATs" while its own create form says "TAX Rate".
VATS_NAV_NAME = "VATs"
VATS_GRID_PANE_NAME = "VATs"
# Mirrors the create form's field labels; not independently probed (the
# rows are UIA-invisible like every other entity's).
VATS_SEARCH_COLUMNS = ["Name", "Value"]

# Fakturama's own nav label, not "Payment methods".
PAYMENT_METHODS_NAV_NAME = "terms of payment"
PAYMENT_METHODS_GRID_PANE_NAME = "terms of payment"
PAYMENT_METHODS_SEARCH_COLUMNS = ["Name"]

# -- Debtor form -------------------------------------------------------------

DEBTOR_NEW_BUTTON_TITLE = "Create a new debtor"
DEBTOR_FORM_CUSTOMER_ID_AUTO_ID = "133128"
DEBTOR_COMPANY_EDIT_NAME = "Company"
DEBTOR_ALIAS_EDIT_NAME = "additional name"
DEBTOR_STREET_EDIT_NAME = "Street"
DEBTOR_COUNTRY_COMBO_NAME = "Country"
# The Edits behind these two labels are blank-named: each label's next
# sibling is the Pane wrapping that row's Edits, left to right.
DEBTOR_NAME_ROW_LABEL_NAME = "First Name Last Name"
DEBTOR_ZIP_CITY_ROW_LABEL_NAME = "ZIP - City"

# -- Product form ------------------------------------------------------------

PRODUCT_NEW_BUTTON_TITLE = "Create a new product"
PRODUCT_SKU_EDIT_NAME = "Item Number"
PRODUCT_NAME_EDIT_NAME = "Name"
PRODUCT_VAT_COMBO_NAME = "VAT"

# This field is Fakturama's GROSS price - confirmed live, a net figure typed
# here came back as net / (1 + VAT) in every Order line built from the
# record. Doubles as a price-basis check: a net-configured Fakturama would
# label it "Price (net)" and find_control would fail closed.
PRODUCT_PRICE_GROSS_LABEL_NAME = "Price (gross)"

# -- VAT rate ("TAX Rate") form ----------------------------------------------

VAT_NEW_BUTTON_TITLE = "Create a new tax rate"
VAT_NAME_EDIT_NAME = "Name"
# Comes pre-filled with "0%", so it must be cleared before typing - typing
# into it inserts, which once made every created rate save as 0% and become
# unfindable by its own resolver.
VAT_VALUE_EDIT_NAME = "Value"

# -- Payment method ("Term of Payment") form ---------------------------------

PAYMENT_NEW_BUTTON_TITLE = "Create a new term of payment"
PAYMENT_NAME_EDIT_NAME = "Name"

# -- Order editor ------------------------------------------------------------
# Fields are pinned by accessible NAME, not auto_id: probing the same editor
# across two launches showed every numeric auto_id changes between sessions
# while the names are identical.

NEW_ORDER_BUTTON_TITLE = "Create: New Order"

# "New Order" until saved, then the assigned order number - both the handle
# for locating a fresh editor and the persistence signal verification checks.
ORDER_TAB_TITLE_UNSAVED = "New Order"

ORDER_CUST_REF_EDIT_NAME = "Cust.Ref."

# Mode-dependent: reads "Total Gross" in the default Gross mode, "Total Net"
# once switched. Pinned to Net so a Gross-mode order fails closed instead of
# silently matching the wrong field.
ORDER_TOTAL_NET_EDIT_NAME = "Total Net"
ORDER_DISCOUNT_EDIT_NAME = "Discount"
ORDER_VAT_EDIT_NAME = "VAT"
ORDER_TOTAL_EDIT_NAME = "Total"

# The pricing-mode combo is blank-named; located via the stable "Date"
# label, two siblings later.
ORDER_DATE_LABEL_NAME = "Date"
ORDER_PRICING_MODE_NET_OPTION = "Net"

# A Debtor is attached by clicking a blank-named Image just after this
# label, not by writing to the customer field (a multi-line address Edit).
ORDER_ADDRESSES_LABEL_NAME = "Addresses"

# The Image right after this label opens the product picker - not the second
# ("add a blank row") Image next to it.
ORDER_ITEMS_LABEL_NAME = "Items"

# -- Order/Invoice items grid ------------------------------------------------
# Cells are located by counting columns off the grid's own drawn separator
# lines (grid_geometry), so the rendered list must match what Fakturama
# draws exactly - including the columns nothing reads.

ITEMS_COL_POSITION = "Pos."
ITEMS_COL_QUANTITY = "Qty."
ITEMS_COL_SKU = "Item No."
ITEMS_COL_PICTURE = "Picture"
ITEMS_COL_NAME = "Name"
ITEMS_COL_DESCRIPTION = "Description"
ITEMS_COL_VAT = "VAT"
ITEMS_COL_UNIT_PRICE = "U.Price"
ITEMS_COL_DISCOUNT = "Discount"
ITEMS_COL_LINE_TOTAL = "Price"

ITEMS_GRID_RENDERED_COLUMNS = [
    ITEMS_COL_POSITION,
    ITEMS_COL_QUANTITY,
    ITEMS_COL_SKU,
    ITEMS_COL_PICTURE,
    ITEMS_COL_NAME,
    ITEMS_COL_DESCRIPTION,
    ITEMS_COL_VAT,
    ITEMS_COL_UNIT_PRICE,
    ITEMS_COL_DISCOUNT,
    ITEMS_COL_LINE_TOTAL,
]

# Renders blank, so row separators can be scanned down it without mistaking
# cell content for a grid line.
ITEMS_GRID_BLANK_COLUMN = ITEMS_COL_PICTURE


def _items_columns(*names: str) -> list[str]:
    """Select named Items-grid columns, in the order given, raising at
    import time on a name that grid does not have - so the subsets below
    cannot drift from the grid they describe.
    """
    unknown = [name for name in names if name not in ITEMS_GRID_RENDERED_COLUMNS]
    if unknown:
        raise ValueError(
            f"{unknown!r} are not columns of the Items grid; known columns are "
            f"{ITEMS_GRID_RENDERED_COLUMNS!r}"
        )
    return list(names)


# What the vision read-back extracts and comparisons check (Task 3.13-3.16).
ITEMS_GRID_READ_COLUMNS = _items_columns(
    ITEMS_COL_SKU,
    ITEMS_COL_QUANTITY,
    ITEMS_COL_UNIT_PRICE,
    ITEMS_COL_VAT,
    ITEMS_COL_DISCOUNT,
    ITEMS_COL_LINE_TOTAL,
)

# Filled by hand after a product is picked: Qty./Discount because the
# catalog record has no per-order values, and Item No. because the picked
# row can carry an internal record number there instead of the SKU
# (confirmed live for a product created in the same run).
ITEMS_GRID_FILL_COLUMNS = _items_columns(
    ITEMS_COL_SKU,
    ITEMS_COL_QUANTITY,
    ITEMS_COL_DISCOUNT,
)

# -- Picker dialogs ----------------------------------------------------------
# Both are separate top-level OS windows (found via win32gui.EnumWindows -
# pywinauto's own enumeration does not reliably see them), structurally
# identical, and both read their UIA-invisible grid through vision_grounding.

ORDER_SELECT_ADDRESS_DIALOG_TITLE = "Select the address"
ORDER_SELECT_ADDRESS_SEARCH_COLUMNS = ["No.", "First Name", "Name", "Company", "ZIP", "City"]
ORDER_SELECT_ADDRESS_COMPANY_COLUMN = "Company"

# Picking here fills Item No./Name/Description/Price/VAT from the catalog
# record - chosen over a blank row filled cell-by-cell, which hit three
# separate live bugs (Doc/adr/0007).
ORDER_SELECT_PRODUCT_DIALOG_TITLE = "Select a product"
ORDER_SELECT_PRODUCT_SEARCH_COLUMNS = ["Item No.", "Name", "Description", "Stock", "Price"]

PICKER_OK_BUTTON_TITLE = "OK"

# -- Invoice editor ----------------------------------------------------------
# Created from the saved Order's "Create a follow-up document" panel; the
# toolbar's own "Create: New Invoice" would not preserve the Order
# relationship (Task 4.6). Shares the Order editor's layout and pricing mode.

INVOICE_FROM_ORDER_BUTTON_TITLE = "Invoice"

# Used both to locate the still-unsaved pane and as the persistence signal.
INVOICE_TAB_TITLE_UNSAVED = "New Invoice"

INVOICE_CUST_REF_EDIT_NAME = "Cust.Ref."
INVOICE_TOTAL_EDIT_NAME = "Total"

# -- Invoice payment fields --------------------------------------------------
# Only these two have a stable name; the payment-method combo and date Edit
# are blank-named and located structurally (see locators.py).

INVOICE_PAID_CHECKBOX_NAME = "paid"
INVOICE_PAYMENT_VALUE_EDIT_NAME = "Value"
INVOICE_PAYMENT_DATE_LABEL_NAME = "at"
