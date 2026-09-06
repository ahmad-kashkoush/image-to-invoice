from __future__ import annotations

import os

# Reuses extraction's Haiku 4.5 default
# screenshot is an even smaller vision task than a full order image.
VISION_GROUNDING_MODEL_ID = os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MODEL", "claude-haiku-4-5")
VISION_GROUNDING_MAX_TOKENS = int(os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MAX_TOKENS", "2048"))

READ_TIMEOUT_SECONDS = float(os.environ.get("FAKTURAMA_UI_AUTOMATION_READ_TIMEOUT_SECONDS", "5.0"))
