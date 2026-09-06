# STUBBED for this build: real OCR re-reading is out of scope, so this is a
from __future__ import annotations

from pathlib import Path

from fakturama_automation.extraction.models import RawOrder


def refine_low_confidence_fields(
    image_path: Path,
    raw_order: RawOrder,
    confidence_threshold: float,
) -> RawOrder:
    # extraction_source is marked so callers/logs can tell OCR was not run.
    raw_order.extraction_source = "vision (ocr fallback stubbed)"
    return raw_order
