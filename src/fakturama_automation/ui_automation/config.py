"""Configuration for ui_automation, specifically vision_grounding.

Section 3 (ui_automation), added alongside Section 4's entity resolution
work. Kept deliberately small and env-driven, mirroring
extraction/config.py and normalization/config.py, so the vision model used
to read custom-rendered grids can change without touching
vision_grounding.py and tests can override it.

Reuses the same model default as extraction/config.py (Claude Haiku 4.5,
chosen for cost - see that module's docstring) since reading a handful of
grid rows from a screenshot is an even smaller vision task than reading a
full order image.
"""

from __future__ import annotations

import os

VISION_GROUNDING_MODEL_ID = os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MODEL", "claude-haiku-4-5")
VISION_GROUNDING_MAX_TOKENS = int(os.environ.get("FAKTURAMA_UI_AUTOMATION_VISION_MAX_TOKENS", "2048"))
