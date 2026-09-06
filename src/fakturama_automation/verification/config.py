"""Tunables for verification.

Control identifiers live in `ui_automation.screens`, shared with the write
path that sets the fields this package reads back.
"""

from __future__ import annotations

import os

VERIFY_SETTLE_SECONDS = float(os.environ.get("FAKTURAMA_VERIFICATION_SETTLE_SECONDS", "1.0"))
DIALOG_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_VERIFICATION_DIALOG_TIMEOUT_SECONDS", "5.0"))
