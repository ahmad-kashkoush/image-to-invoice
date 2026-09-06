"""Configuration for ui_automation.vision_grounding.

Reuses extraction/config.py's Haiku 4.5 default - reading a handful of grid
rows from a screenshot is an even smaller vision task than a full order image.
"""

from __future__ import annotations

import os

VISION_GROUNDING_MODEL_ID = os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MODEL", "claude-haiku-4-5")
VISION_GROUNDING_MAX_TOKENS = int(os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MAX_TOKENS", "2048"))
