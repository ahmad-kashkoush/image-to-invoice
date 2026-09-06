from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.extraction.vision_extractor import extract_from_image


def _tool_use_block(input_data: dict, name: str = "record_order") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_data)


def _text_block() -> SimpleNamespace:
    return SimpleNamespace(type="text", text="hello")


class FakeMessages:
    def __init__(self, response: SimpleNamespace | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, response: SimpleNamespace | None = None, error: Exception | None = None) -> None:
        self.messages = FakeMessages(response=response, error=error)


ADDR_CONF = {"street": 0.9, "postal_code": 0.9, "city": 0.9, "country": 0.9}
LINE_CONF = {
    "sku": 0.9,
    "description": 0.9,
    "quantity": 0.9,
    "unit_net_price": 0.9,
    "vat_percent": 0.9,
    "discount": 0.9,
    "source_line_total": 0.9,
}
ORDER_CONF = {
    "order_date": 0.9,
    "external_reference": 0.9,
    "debtor_company_name": 0.9,
    "contact_name": 0.9,
    "alias": 0.9,
    "payment_details": 0.9,
    "payment_method": 0.9,
    "payment_status": 0.9,
    "payment_date": 0.9,
}


def _happy_path_input() -> dict:
    return {
        "order_date": "2026-03-04",
        "external_reference": "PO-123",
        "debtor_company_name": "Acme Corp",
        "contact_name": "Jane Doe",
        "alias": None,
        "billing_address": {
            "raw_text": "1 Main St",
            "street": "1 Main St",
            "postal_code": "12345",
            "city": "Springfield",
            "country": "US",
            "confidence": ADDR_CONF,
        },
        "delivery_address": {
            "raw_text": "",
            "street": None,
            "postal_code": None,
            "city": None,
            "country": None,
            "confidence": {},
        },
        "payment_details": None,
        "payment_method": "bank transfer",
        "payment_status": "UNPAID",
        "payment_date": None,
        "line_items": [
            {
                "sku": "SKU1",
                "description": "Widget",
                "quantity": "2",
                "unit_net_price": "9.99",
                "vat_percent": "19",
                "discount": "0",
                "source_line_total": "19.98",
                "confidence": LINE_CONF,
            }
        ],
        "confidence": ORDER_CONF,
    }


def test_happy_path_maps_fields_and_clamps_confidence(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")

    response = SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block(_happy_path_input())])
    client = FakeClient(response=response)

    raw_order = extract_from_image(image_path, client=client)

    assert raw_order.source_image_path == str(image_path)
    assert raw_order.debtor_company_name == "Acme Corp"
    assert raw_order.billing_address.city == "Springfield"
    assert raw_order.billing_address.confidence["city"] == 0.9
    assert raw_order.delivery_address.street is None
    assert len(raw_order.line_items) == 1
    assert raw_order.line_items[0].sku == "SKU1"
    assert raw_order.confidence["debtor_company_name"] == 0.9
    # never guessed
    assert raw_order.alias is None


def test_missing_confidence_keys_default_to_zero(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")
    data = _happy_path_input()
    data["confidence"] = {}  # nothing reported

    response = SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block(data)])
    client = FakeClient(response=response)

    raw_order = extract_from_image(image_path, client=client)

    assert raw_order.confidence["debtor_company_name"] == 0.0


def test_out_of_range_confidence_is_clamped(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")
    data = _happy_path_input()
    data["confidence"]["debtor_company_name"] = 5.0

    response = SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block(data)])
    client = FakeClient(response=response)

    raw_order = extract_from_image(image_path, client=client)

    assert raw_order.confidence["debtor_company_name"] == 1.0


def test_no_tool_use_block_raises_manual_review(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")

    response = SimpleNamespace(stop_reason="end_turn", content=[_text_block()])
    client = FakeClient(response=response)

    with pytest.raises(ManualReviewRequired):
        extract_from_image(image_path, client=client)


def test_wrong_tool_name_raises_manual_review(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")

    response = SimpleNamespace(
        stop_reason="tool_use", content=[_tool_use_block({}, name="something_else")]
    )
    client = FakeClient(response=response)

    with pytest.raises(ManualReviewRequired):
        extract_from_image(image_path, client=client)


def test_refusal_raises_manual_review(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")

    response = SimpleNamespace(stop_reason="refusal", content=[])
    client = FakeClient(response=response)

    with pytest.raises(ManualReviewRequired):
        extract_from_image(image_path, client=client)


def test_api_error_raises_manual_review(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")

    client = FakeClient(error=RuntimeError("boom"))

    with pytest.raises(ManualReviewRequired):
        extract_from_image(image_path, client=client)


def test_unsupported_image_extension_raises_manual_review(tmp_path: Path) -> None:
    image_path = tmp_path / "order.gif"
    image_path.write_bytes(b"fake-gif-bytes")

    with pytest.raises(ManualReviewRequired):
        extract_from_image(image_path, client=FakeClient(response=SimpleNamespace(content=[])))


def test_malformed_tool_input_raises_manual_review(tmp_path: Path) -> None:
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")

    # line_items entries must be dicts; a plain string breaks _line_item_from_dict
    data = _happy_path_input()
    data["line_items"] = ["not-a-dict"]
    response = SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block(data)])
    client = FakeClient(response=response)

    with pytest.raises(ManualReviewRequired):
        extract_from_image(image_path, client=client)
