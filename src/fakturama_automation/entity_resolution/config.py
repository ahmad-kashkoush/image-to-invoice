"""Configuration for entity resolution.

Section 4 (entity_resolution). Kept deliberately small and env-driven,
mirroring normalization/config.py and extraction/config.py, so timeouts can
change without touching the resolvers and tests can override them.

The per-entity selector constants below are pywinauto identifiers pinned
from probes/probe-*.txt (captured on the Windows 11 ARM VM against a real
Fakturama window - see probes/probe-06-debitors.txt, probe-07-products.txt,
probe-08-vats.txt, probe-0801-vats.txt, probe-09-Payment.txt,
probe-10-payment-create-form.txt, probes/probe-03/04-*-debitor.txt).
Debtor, Product, VAT, and Payment are all now fully probed and pinned.
Keeping every selector here (not inline in each resolver module) means a
future re-probe only touches this file.
"""

from __future__ import annotations

import os

# -- timeouts / polling --------------------------------------------------

SEARCH_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_SEARCH_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_DIALOG_TIMEOUT_SECONDS", "5.0"))

# -- shared across every entity screen -----------------------------------

# Every Fakturama screen lives inside this one top-level window; the path
# suffix ("D:\Projects\fakturama-data") is environment-specific, so this is
# a prefix match rather than an exact title.
APP_TITLE_RE = r"^Fakturama - "

# The bottom list-editor TabControl is always this auto_id regardless of
# which list (Debtors/Products/terms of payment/...) is currently active;
# its *title* changes with the active list, so select the intended nav
# TabItem first, then disambiguate by the entity-specific content pane
# auto_id below - never by this shared auto_id alone.
LIST_EDITOR_TAB_AUTO_ID = "525638"

# No auto_id on this button anywhere it appears (confirmed identical across
# every probed screen) - select by title only.
SAVE_BUTTON_TITLE = "Save the current contents"

# -- Debtor (probes/probe-06-debitors.txt, probe-03/04-*-debitor.txt) ----

DEBTOR_LIST_PANE_AUTO_ID = "723164"
DEBTOR_SEARCH_EDIT_AUTO_ID = "67910"  # blank-named Edit; addressed by auto_id only
DEBTOR_NEW_BUTTON_TITLE = "Create a new debtor"
DEBTOR_FORM_COMPANY_AUTO_ID = "133110"
DEBTOR_FORM_CUSTOMER_ID_AUTO_ID = "133128"
DEBTOR_FORM_FIRST_NAME_AUTO_ID = "132966"  # blank-named Edit
DEBTOR_FORM_LAST_NAME_AUTO_ID = "132968"  # blank-named Edit
DEBTOR_FORM_ALIAS_AUTO_ID = "133056"  # "additional name"
DEBTOR_FORM_STREET_AUTO_ID = "133048"
DEBTOR_FORM_ZIP_AUTO_ID = "132992"  # blank-named Edit
DEBTOR_FORM_CITY_AUTO_ID = "132990"  # blank-named Edit
DEBTOR_FORM_COUNTRY_COMBO_AUTO_ID = "132980"

# -- Product (probes/probe-07-products.txt) -------------------------------

PRODUCT_LIST_PANE_AUTO_ID = "199058"
PRODUCT_SEARCH_EDIT_AUTO_ID = "68006"  # blank-named Edit
PRODUCT_NEW_BUTTON_TITLE = "Create a new product"
PRODUCT_FORM_SKU_AUTO_ID = "133748"  # "Item Number"
PRODUCT_FORM_NAME_AUTO_ID = "133744"
PRODUCT_FORM_VAT_COMBO_AUTO_ID = "133754"
PRODUCT_FORM_PRICE_AUTO_ID = "133802"  # blank-named Edit ("Price (gross)")

# -- VAT rate (re-probed with the VATs list/create form open - -----------
# -- probes/probe-08-vats.txt (list), probe-0801-vats.txt (create form). -
# -- Fakturama calls this entity "TAX Rate" in its own create form, even -
# -- though its own nav label and every other screen say "VATs". --------

VAT_LIST_PANE_AUTO_ID = "723642"
VAT_SEARCH_EDIT_AUTO_ID = "133830"  # blank-named Edit
VAT_NEW_BUTTON_TITLE = "Create a new tax rate"
VAT_FORM_NAME_AUTO_ID = "133868"  # "Name"
VAT_FORM_PERCENT_AUTO_ID = "199168"  # "Value"

# -- Payment method / "terms of payment" (probes/probe-09-Payment.txt: ---
# -- list view; probes/probe-10-payment-create-form.txt: create form, ----
# -- captured as Fakturama's own "New Term of Payment" editor) -----------

PAYMENT_LIST_PANE_AUTO_ID = "854450"
PAYMENT_SEARCH_EDIT_AUTO_ID = "68042"  # blank-named Edit
PAYMENT_NEW_BUTTON_TITLE = "Create a new term of payment"
PAYMENT_FORM_NAME_AUTO_ID = "66848"  # "Name"; Account/Description/Cash
# discount/Discount Days/Net Days are all optional and left unfilled.
