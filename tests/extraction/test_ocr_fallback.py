"""Tests for the (stubbed) OCR fallback pass.

See ocr_fallback.py's module docstring: this is a documented no-op for
this demo build, not a real OCR implementation.
"""

from __future__ import annotations

from pathlib import Path

from fakturama_automation.extraction.models import RawLineItem, RawOrder
from fakturama_automation.extraction.ocr_fallback import refine_low_confidence_fields


def test_stub_returns_order_unchanged_except_provenance(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    order = RawOrder(
        source_image_path=str(image_path),
        debtor_company_name="Acme Corp",
        line_items=[RawLineItem(sku="SKU1", confidence={"sku": 0.2})],
        confidence={"debtor_company_name": 0.1},
    )

    result = refine_low_confidence_fields(image_path, order, confidence_threshold=0.75)

    assert result is order
    assert result.debtor_company_name == "Acme Corp"
    assert result.line_items[0].sku == "SKU1"
    # low confidence values are left as-is - normalization.validators is
    # responsible for routing them to manual review, not this stub.
    assert result.confidence["debtor_company_name"] == 0.1
    assert result.line_items[0].confidence["sku"] == 0.2
    assert "stubbed" in result.extraction_source
