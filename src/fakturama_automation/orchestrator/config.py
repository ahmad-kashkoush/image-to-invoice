"""Tunables for the orchestrator's workflow steps.

Control identifiers live in `ui_automation.screens`. What remains is timing
and retry policy, tuned against a live Fakturama.
"""

from __future__ import annotations

import os

# -- timeouts / polling ------------------------------------------------------

SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_TIMEOUT_SECONDS", "5.0"))

# How long a just-opened picker dialog must stay visible before it's
# trusted as actually open, and how many times to re-click if not (the
# "Select a product"/"Select the address" pickers can flash open and close
# within a fraction of a second of the toolbar click that opens them).
DIALOG_STABILIZE_SECONDS = float(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_STABILIZE_SECONDS", "0.3"))
DIALOG_OPEN_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_DIALOG_OPEN_ATTEMPTS", "3"))

# -- items grid --------------------------------------------------------------

# Re-measure the grid from a fresh screenshot and refill if the read-back
# afterwards disagrees.
ORDER_LINE_FILL_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_LINE_FILL_ATTEMPTS", "2"))

# Measuring is a read, so a bad frame is retried rather than failed on:
# capturing right after the picker closes can catch the grid mid-relayout,
# which measured as 8 columns of a 10-column grid live. A genuinely clipped
# grid still fails closed after these attempts.
GRID_MEASURE_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_GRID_MEASURE_ATTEMPTS", "3"))

# -- editors -----------------------------------------------------------------

# Re-selecting an editor tab can silently not take - see
# ui_automation.controls.reactivate_editor.
EDITOR_ACTIVATE_ATTEMPTS = int(os.environ.get("FAKTURAMA_ORCHESTRATOR_EDITOR_ACTIVATE_ATTEMPTS", "3"))
