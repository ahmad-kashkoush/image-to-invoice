"""Configuration for entity resolution.

Per-entity selector constants are pywinauto identifiers pinned from live VM
probes (probes/probe-*.txt); kept here rather than inline so a re-probe
only touches this file.
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

DEBTOR_NEW_BUTTON_TITLE = "Create a new debtor"
DEBTOR_FORM_CUSTOMER_ID_AUTO_ID = "133128"

# -- Product ---------------------------------------------------------------
# Item Number/Name/VAT-combo are selected by accessible name, not auto_id
# (auto_ids are session-unstable - see product.py). Only "Price (gross)" is
# genuinely blank-named, so it's located structurally in product.py.

PRODUCT_NEW_BUTTON_TITLE = "Create a new product"

# The product's price field is Fakturama's GROSS price - the label says so
# literally, and a live run confirmed it behaves that way: a net figure
# typed here came back as net / (1 + VAT) in every Order line built from
# that catalog record. product.py converts net -> gross before typing
# (normalization.validators.gross_from_net). Doubles as the price-basis
# check: if this app were ever configured for net-price entry the label
# would read "Price (net)" and find_control would fail closed rather than
# silently writing a net figure into a gross field.
PRODUCT_PRICE_GROSS_LABEL_NAME = "Price (gross)"

# -- VAT rate ---------------------------------------------------------------
# Fakturama's own create form calls this entity "TAX Rate", though its nav
# label says "VATs". Name/Value selected by accessible name, same reason as
# Product above - see vat_rate.py.

VAT_NEW_BUTTON_TITLE = "Create a new tax rate"

# -- Payment method / "terms of payment" ------------------------------------

PAYMENT_NEW_BUTTON_TITLE = "Create a new term of payment"
# Account/Description/Cash discount/Discount Days/Net Days are optional, unfilled.
