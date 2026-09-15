
from __future__ import annotations

# -- Application -------------------------------------------------------------

# Prefix match: the title's path suffix is environment-specific.
APP_TITLE_RE = r"^Fakturama - "

# -- Shared across every screen ----------------------------------------------
SAVE_BUTTON_TITLE = "Save the current contents"
SEARCH_LABEL_NAME = "Search:"

# -- Navigation View: the entity list screens --------------------------------
DEBTORS_NAV_NAME = "Debtors"
DEBTORS_GRID_PANE_NAME = "Debtors"
DEBTORS_SEARCH_COLUMNS = ["No.", "First Name", "Name", "Company", "ZIP", "City"]

PRODUCTS_NAV_NAME = "Products"
PRODUCTS_GRID_PANE_NAME = "Products"
PRODUCTS_SEARCH_COLUMNS = ["Item Number"]

# Fakturama's nav says "VATs" while its own create form says "TAX Rate".
VATS_NAV_NAME = "VATs"
VATS_GRID_PANE_NAME = "VATs"
# Mirrors the create form's field labels; not independently probed (the
# rows are UIA-invisible like every other entity's).
VATS_SEARCH_COLUMNS = ["Name", "Value"]

# -- Navigation View: Data > Documents ---------------------------------------
# The saved Order/Invoice list, and the one list screen that does not follow
# the triple above. Two things are different (probes/probe-15-documents-list.txt,
# probes/probe_documents_output/):
#
#  - Pane 'Documents' holds a document-type Tree as well as the grid, so it
#    cannot be captured whole - see locators.documents_grid_pane.
#  - That tree *scopes the search box*. Typing an invoice number while Orders
#    is selected returns nothing (captured: documents-Orders-INV000002-rows.png
#    is empty, documents-Invoices-INV000002-rows.png has the row), so the node
#    has to be selected before searching. It also means a search can never
#    return a document of the wrong type.
DOCUMENTS_NAV_NAME = "Documents"
DOCUMENTS_GRID_PANE_NAME = "Documents"
DOCUMENTS_ORDERS_TREE_ITEM = "Orders"
DOCUMENTS_INVOICES_TREE_ITEM = "Invoices"

DOCUMENTS_COL_NUMBER = "Document"
DOCUMENTS_COL_DATE = "Date"
DOCUMENTS_COL_CUSTOMER_REF = "Cust.Ref."
DOCUMENTS_COL_STATE = "State"
DOCUMENTS_COL_TOTAL = "Total"
# A subset of what the grid renders - the full order is an unnamed icon
# column, Document, Date, Name, Cust.Ref., State, Total, Printed, and a
# trailing filler. Name and Printed are not read: nothing compares them, and
# every column read is a column whose clipping has to be dealt with.
DOCUMENTS_READ_COLUMNS = [
    DOCUMENTS_COL_NUMBER,
    DOCUMENTS_COL_DATE,
    DOCUMENTS_COL_CUSTOMER_REF,
    DOCUMENTS_COL_STATE,
    DOCUMENTS_COL_TOTAL,
]

# What the State cell renders. Both confirmed live 2026-09-15: every Order row
# reads "open", every paid Invoice row reads "paid". The word an *unpaid*
# Invoice shows has never been seen - no workspace probed has one - so
# verification checks "not paid" for that case rather than guessing a third
# constant into existence.
DOCUMENT_STATE_OPEN = "open"
DOCUMENT_STATE_PAID = "paid"

# Fakturama's own nav label, not "Payment methods".
PAYMENT_METHODS_NAV_NAME = "terms of payment"
PAYMENT_METHODS_GRID_PANE_NAME = "terms of payment"
PAYMENT_METHODS_SEARCH_COLUMNS = ["Name"]

# -- Debtor form -------------------------------------------------------------

DEBTOR_NEW_BUTTON_TITLE = "Create a new debtor"
# Has a real accessible name ("Customer ID") per
# probes/probe-04-fill-create-debitor.txt - unlike this app's blank-named
# controls, no need for its (session-unstable) auto_id.
DEBTOR_CUSTOMER_ID_EDIT_NAME = "Customer ID"
DEBTOR_COMPANY_EDIT_NAME = "Company"
DEBTOR_ALIAS_EDIT_NAME = "additional name"
DEBTOR_STREET_EDIT_NAME = "Street"
DEBTOR_COUNTRY_COMBO_NAME = "Country"
DEBTOR_NAME_ROW_LABEL_NAME = "First Name Last Name"
DEBTOR_ZIP_CITY_ROW_LABEL_NAME = "ZIP - City"

# -- Product form ------------------------------------------------------------

PRODUCT_NEW_BUTTON_TITLE = "Create a new product"
PRODUCT_SKU_EDIT_NAME = "Item Number"
PRODUCT_NAME_EDIT_NAME = "Name"
PRODUCT_VAT_COMBO_NAME = "VAT"
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
# Which term a new document inherits. Fakturama assigns it at construction
# from the profile's standard, and the Order editor offers no control to
# change it afterwards (probed 2026-09-15: 74 descendants, three combos -
# pricing mode, VAT, Shipping - and nothing payment-related, on both an
# unsaved and a saved Order). Setting the standard is therefore the only
# lever there is; see entity_resolution/payment_method.py.
PAYMENT_STANDARD_COLUMN = "Standard"
PAYMENT_METHODS_LIST_COLUMNS = [PAYMENT_STANDARD_COLUMN, PAYMENT_NAME_EDIT_NAME]
PAYMENT_SET_STANDARD_BUTTON_TITLE = "Set as standard"

# -- Order editor ------------------------------------------------------------
NEW_ORDER_BUTTON_TITLE = "Create: New Order"

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


def _items_columns(*names: str) -> list[str]:
    # Raises at import time on a name the grid does not have, so the subsets
    # below cannot drift from the grid they describe.
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
