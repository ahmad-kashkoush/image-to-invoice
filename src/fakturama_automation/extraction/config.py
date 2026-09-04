"""Configuration for the vision extraction pass.

Section 1 (extraction). Kept deliberately small and env-driven so defaults
can change without touching vision_extractor.py, and so tests can override
them. API key resolution is left entirely to the anthropic SDK (it reads
ANTHROPIC_API_KEY, or an `ant auth login` profile) - nothing here handles
secrets.

MODEL_ID defaults to Claude Haiku 4.5 rather than a larger model: this
extraction module targets a low-cost demo build, not a production
deployment, and Haiku is vision-capable and far cheaper than Opus/Sonnet
while being sufficient for reading a single order image.
"""

from __future__ import annotations

import os

MODEL_ID = os.environ.get("FAKTURAMA_EXTRACTION_MODEL", "claude-haiku-4-5")
MAX_TOKENS = int(os.environ.get("FAKTURAMA_EXTRACTION_MAX_TOKENS", "4096"))
