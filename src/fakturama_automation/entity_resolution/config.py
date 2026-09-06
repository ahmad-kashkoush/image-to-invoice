from __future__ import annotations

import os

# How long to let Fakturama's custom-rendered results grid re-render after
# typing into a search box, before screenshotting it. A short fixed delay
# rather than a poll, deliberately: the grid's UIA-invisibility is exactly
# the problem, so there is no signal to poll for, and polling would mean
# firing a vision API call per poll (Doc/adr/0003 Decision 2).
SEARCH_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_SEARCH_SETTLE_SECONDS", "1.0"))

DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_ENTITY_RESOLUTION_DIALOG_TIMEOUT_SECONDS", "5.0"))
