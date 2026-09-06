"""Configuration for the vision extraction pass.

MODEL_ID defaults to Haiku 4.5, not a larger model: vision-capable and far
cheaper than Opus/Sonnet, sufficient for reading a single order image.
"""

from __future__ import annotations

import os

MODEL_ID = os.environ.get("FAKTURAMA_EXTRACTION_MODEL", "claude-haiku-4-5")
MAX_TOKENS = int(os.environ.get("FAKTURAMA_EXTRACTION_MAX_TOKENS", "4096"))
