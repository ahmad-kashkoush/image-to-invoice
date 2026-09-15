from __future__ import annotations

import os
SEARCH_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_SEARCH_SETTLE_SECONDS", "1.0"))

DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_DIALOG_TIMEOUT_SECONDS", "5.0"))

# How far to drag a list grid's column separator when its cells render
# clipped (see ui_automation/grid_columns.py). Wide enough for a long company
# name; the grids this runs against have unused space to their right.
COLUMN_WIDEN_PIXELS = int(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_COLUMN_WIDEN_PIXELS", "150"))
