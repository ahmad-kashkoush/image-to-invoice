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
    from fakturama_automation.extraction.ocr_fallback import refine_low_confidence_fields
    from fakturama_automation.extraction.vision_extractor import extract_from_image

    raw_order = extract_from_image(image_path, client=client)
    return refine_low_confidence_fields(image_path, raw_order, confidence_threshold)
