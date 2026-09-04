"""Extraction package.

Reads a single order image and produces raw structured data using a vision
capable LLM (Claude Haiku 4.5, chosen for cost - see config.py), with OCR
as a low confidence fallback. See section 1 of the project plan.

Note: the OCR fallback pass (ocr_fallback.py) is currently a stub for this
demo build - see that module's docstring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fakturama_automation.extraction.models import RawOrder
from fakturama_automation.extraction.ocr_fallback import refine_low_confidence_fields
from fakturama_automation.extraction.vision_extractor import extract_from_image

DEFAULT_CONFIDENCE_THRESHOLD = 0.75


def extract_order(
    image_path: Path,
    *,
    client: Any | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> RawOrder:
    """Run the full extraction pass for a single order image: vision LLM
    first, then the OCR fallback for any fields below confidence_threshold.

    This is the single entry point normalization/orchestrator should call.
    """
    raw_order = extract_from_image(image_path, client=client)
    return refine_low_confidence_fields(image_path, raw_order, confidence_threshold)
