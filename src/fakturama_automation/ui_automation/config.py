from __future__ import annotations

import os

# Reuses extraction's Haiku 4.5 default
# screenshot is an even smaller vision task than a full order image.
VISION_GROUNDING_MODEL_ID = os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MODEL", "claude-haiku-4-5")
VISION_GROUNDING_MAX_TOKENS = int(os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MAX_TOKENS", "2048"))

READ_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_UI_AUTOMATION_READ_TIMEOUT_SECONDS", "5.0"))

# How long a list screen takes to re-filter after its search box is typed
# into, and how long to wait for its grid pane to appear (list_grids.py).
LIST_GRID_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_UI_AUTOMATION_LIST_GRID_SETTLE_SECONDS", "1.0"))
LIST_GRID_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_UI_AUTOMATION_LIST_GRID_TIMEOUT_SECONDS", "5.0"))

# How far to drag a list grid's column separator when its cells render
# clipped (see grid_columns.py). Wide enough for a long company name; the
# grids this runs against have unused space to their right.
COLUMN_WIDEN_PIXELS = int(os.environ.get("FAKTURAMA_UI_AUTOMATION_COLUMN_WIDEN_PIXELS", "150"))

# The decimal separator Fakturama's *form fields* parse and render -
# a fact about the running app, not about the documents being read, which is
# why it lives here and not in normalization/config.py. Default "," for the
# de-DE install this targets: a fresh Product form's empty Price (gross)
# reads "0,00 EUR", and typing "297.50" there is parsed as 29750.
#
# It is deliberately NOT global. Measured live 2026-09-15, Fakturama is not
# internally consistent, and the line is drawn between *form Edits* and
# *grid cells*, not between master data and documents:
#   - form Edits parse ",": the Product price, and the Invoice payment Value
#     (which turned "678.30" into "67.830,00")
#   - the Order editor's Items grid parses "." and renders "45,000.00";
#     typing "2,00" into its Qty. cell yields 200
# So pair this with normalization.parsing.format_decimal for form Edits, and
# leave grid cells on a plain str() - see orchestrator/steps/items_grid.py.
# Reading back is locale-agnostic already (parse_money_text handles both).
DECIMAL_SEPARATOR = os.environ.get("FAKTURAMA_UI_AUTOMATION_DECIMAL_SEPARATOR", ",")
