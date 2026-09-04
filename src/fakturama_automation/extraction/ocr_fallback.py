"""OCR fallback pass for low confidence fields from the vision LLM.

Section 1 (extraction), secondary pass.

STUBBED for this build: this is a pre-interview demo, not a production
system, so real OCR re-reading (Tesseract or similar) is out of scope here
and this function is a documented no-op pass-through. It is kept callable
(rather than raising) so an orchestrator can call it unconditionally
without special-casing "OCR not implemented".

This does not weaken correctness: fields left at low confidence are still
caught by normalization/validators.py::check_confidence and routed to
manual review rather than silently accepted. Real OCR would only have
*recovered* some of those cases (by cross-checking a genuinely ambiguous
field against a second source) - it does not gate correctness, the
recomputation in check_line_total and the confidence check both still fail
closed without it.
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
