from __future__ import annotations

import os

MODEL_ID = os.environ.get("FAKTURAMA_EXTRACTION_MODEL", "claude-haiku-4-5")
MAX_TOKENS = int(os.environ.get("FAKTURAMA_EXTRACTION_MAX_TOKENS", "4096"))
