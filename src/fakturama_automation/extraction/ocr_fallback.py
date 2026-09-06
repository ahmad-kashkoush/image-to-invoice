"""OCR fallback pass for low confidence fields from the vision LLM.

STUBBED for this build: real OCR re-reading (Tesseract or similar) is out
of scope, so this is a documented no-op pass-through - kept callable
(rather than raising) so an orchestrator can call it unconditionally.
Correctness doesn't depend on it: fields left at low confidence are still
caught by normalization/validators.py::check_confidence and routed to
manual review.
"""

from __future__ import annotations

from pathlib import Path

from fakturama_automation.extraction.models import RawOrder


def refine_low_confidence_fields(
    image_path: Path,
    raw_order: RawOrder,
    confidence_threshold: float,
) -> RawOrder:
    """No-op stub: returns raw_order unchanged.

    Real OCR-based refinement of fields below confidence_threshold is not
    implemented in this build (see module docstring). Marks
    extraction_source so callers/logs can tell OCR was not run.
    """
    raw_order.extraction_source = "vision (ocr fallback stubbed)"
    return raw_order
