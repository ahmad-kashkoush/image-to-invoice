"""Extraction package.

Reads a single order image and produces raw structured data using a vision
capable LLM, with OCR as a low confidence fallback (currently a stub for
this demo build - see ocr_fallback.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fakturama_automation.extraction.models import RawOrder

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

    The two implementation modules are imported here rather than at module
    level so that `extraction.models` - which normalization.validators reads
    the confidence field lists from - can be imported without pulling in the
    Anthropic SDK. Same reasoning as the deferred pywinauto import in
    orchestrator.state_machine (Doc/adr/0007 Decision 4): the heavy
    dependency of an adapter should load when the adapter is called, not
    when something merely names its data shapes.
    """
    from fakturama_automation.extraction.ocr_fallback import refine_low_confidence_fields
    from fakturama_automation.extraction.vision_extractor import extract_from_image

    raw_order = extract_from_image(image_path, client=client)
    return refine_low_confidence_fields(image_path, raw_order, confidence_threshold)
