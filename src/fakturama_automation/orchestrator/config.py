from __future__ import annotations

import os

# -- timeouts / polling ------------------------------------------------------

SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_TIMEOUT_SECONDS", "5.0"))

DIALOG_STABILIZE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_STABILIZE_SECONDS", "0.3"))
DIALOG_OPEN_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_OPEN_ATTEMPTS", "3"))

# -- items grid --------------------------------------------------------------

ORDER_LINE_FILL_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_LINE_FILL_ATTEMPTS", "2"))

GRID_MEASURE_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_GRID_MEASURE_ATTEMPTS", "3"))

# -- editors -----------------------------------------------------------------

EDITOR_ACTIVATE_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_EDITOR_ACTIVATE_ATTEMPTS", "3"))
