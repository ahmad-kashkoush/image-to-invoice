"""Vision LLM based extraction of order data from a single image.

Uses a vision LLM (see config.py) via the anthropic SDK, forcing a single
structured tool call (`record_order`) so the response is parsed as a dict
rather than free text. Every field the model could not read is left None
(never guessed), with a self-reported per-field confidence.

Confidence is the model's own self-assessment, not a calibrated
probability - it only decides what warrants a closer look, never proof a
value is correct. The real correctness gate for line items is the
deterministic recomputation in normalization/validators.py::check_line_total.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import anthropic

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.extraction import config
from fakturama_automation.extraction.models import (
    ADDRESS_CONFIDENCE_FIELDS,
    LINE_ITEM_CONFIDENCE_FIELDS,
    ORDER_LEVEL_CONFIDENCE_FIELDS,
    RawAddress,
    RawLineItem,
    RawOrder,
)

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_ADDRESS_SCHEMA = {
    "type": "object",
    "properties": {
        "raw_text": {"type": "string"},
        "street": {"type": ["string", "null"]},
        "postal_code": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "confidence": {
            "type": "object",
            "properties": {f: {"type": "number"} for f in ADDRESS_CONFIDENCE_FIELDS},
            "required": ADDRESS_CONFIDENCE_FIELDS,
            "additionalProperties": False,
        },
    },
    "required": ["raw_text", "street", "postal_code", "city", "country", "confidence"],
    "additionalProperties": False,
}

_LINE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "sku": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "quantity": {"type": ["string", "null"]},
        "unit_net_price": {"type": ["string", "null"]},
        "vat_percent": {"type": ["string", "null"]},
        "discount": {"type": ["string", "null"]},
        "source_line_total": {"type": ["string", "null"]},
        "confidence": {
            "type": "object",
            "properties": {f: {"type": "number"} for f in LINE_ITEM_CONFIDENCE_FIELDS},
            "required": LINE_ITEM_CONFIDENCE_FIELDS,
            "additionalProperties": False,
        },
    },
    "required": [
        "sku",
        "description",
        "quantity",
        "unit_net_price",
        "vat_percent",
        "discount",
        "source_line_total",
        "confidence",
    ],
    "additionalProperties": False,
}

_RECORD_ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "order_date": {"type": ["string", "null"], "description": "Order date as printed, e.g. '2026-03-04' or '04.03.2026'."},
        "external_reference": {"type": ["string", "null"]},
        "debtor_company_name": {"type": ["string", "null"]},
        "contact_name": {"type": ["string", "null"]},
        "alias": {"type": ["string", "null"]},
        "billing_address": _ADDRESS_SCHEMA,
        "delivery_address": _ADDRESS_SCHEMA,
        "payment_details": {"type": ["string", "null"], "description": "IBAN/BIC or other payment detail free text."},
        "payment_method": {"type": ["string", "null"]},
        "payment_status": {"type": ["string", "null"], "description": "e.g. PAID, UNPAID, PENDING, as stated or implied on the document."},
        "payment_date": {"type": ["string", "null"]},
        "line_items": {"type": "array", "items": _LINE_ITEM_SCHEMA},
        "confidence": {
            "type": "object",
            "properties": {f: {"type": "number"} for f in ORDER_LEVEL_CONFIDENCE_FIELDS},
            "required": ORDER_LEVEL_CONFIDENCE_FIELDS,
            "additionalProperties": False,
        },
    },
    "required": [
        "order_date",
        "external_reference",
        "debtor_company_name",
        "contact_name",
        "alias",
        "billing_address",
        "delivery_address",
        "payment_details",
        "payment_method",
        "payment_status",
        "payment_date",
        "line_items",
        "confidence",
    ],
    "additionalProperties": False,
}

_RECORD_ORDER_TOOL = {
    "name": "record_order",
    "description": (
        "Record every field extracted from the order image. Call this exactly once with "
        "everything you found."
    ),
    "input_schema": _RECORD_ORDER_SCHEMA,
    # No "strict": True - this schema's ~24 nullable/union-typed fields (every
    # extracted value can be null, per this module's "never guess" rule)
    # exceed the API's strict-mode compilation limit (400: "too many
    # parameters with union types ... limit: 16"). tool_choice below already
    # forces the single record_order call; every _*_from_dict parser already
    # reads via .get(...) with fail-closed defaults rather than trusting
    # schema-guaranteed shape, so non-strict tool use needs no other change.
}

_EXTRACTION_PROMPT = """\
This image is a single scanned or photographed purchase order. Extract the following, exactly as printed:

- Order date and external reference (order/PO number).
- Debtor company name, contact name, alias, billing address, and delivery address.
- Payment method, payment status, payment date (if present), and any payment details (IBAN/BIC etc.).
- For every line item: SKU, description, quantity, unit net price, VAT percent, discount, and the \
source line total exactly as printed.

Rules:
- Do not infer, guess, or complete a value that is not visibly present on the document. A field you \
cannot read is null.
- For every field (including each address sub-field and each line item field), also give a confidence \
between 0.0 and 1.0 reflecting how legibly and unambiguously you could read that specific value. Use a \
low confidence for smudged, handwritten, cut-off, or ambiguous text - do not default to a high confidence.
- Call the record_order tool exactly once with the complete result.
"""


def extract_from_image(image_path: Path, *, client: Any | None = None) -> RawOrder:
    """Run the vision LLM extraction pass on a single order image.

    `client` is injectable (an anthropic-compatible client, or a test
    double exposing `.messages.create(...)`) so this can be tested without
    a real API key or network access; it defaults to a real
    `anthropic.Anthropic()` client.
    """
    media_type = _media_type_for(image_path)
    image_b64 = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    if client is None:
        client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=config.MODEL_ID,
            max_tokens=config.MAX_TOKENS,
            tools=[_RECORD_ORDER_TOOL],
            tool_choice={"type": "tool", "name": "record_order"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": _EXTRACTION_PROMPT},
                    ],
                }
            ],
        )
    except Exception as exc:  # anthropic.APIError and friends, or a fake client's own errors
        raise ManualReviewRequired(step="extraction", reason=f"vision LLM call failed: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise ManualReviewRequired(step="extraction", reason="vision LLM refused the request")

    tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if not tool_use_blocks:
        raise ManualReviewRequired(
            step="extraction", reason="vision LLM did not return a record_order tool call"
        )

    block = tool_use_blocks[0]
    if block.name != "record_order":
        raise ManualReviewRequired(step="extraction", reason=f"unexpected tool call '{block.name}'")

    try:
        return _raw_order_from_tool_input(block.input, source_image_path=str(image_path))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ManualReviewRequired(step="extraction", reason=f"malformed extraction result: {exc}") from exc


def _media_type_for(image_path: Path) -> str:
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower())
    if media_type is None:
        raise ManualReviewRequired(
            step="extraction", reason=f"unsupported image type: '{image_path.suffix}'"
        )
    return media_type


def _clamp_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _confidence_dict(raw: dict[str, Any], keys: list[str]) -> dict[str, float]:
    return {key: _clamp_confidence(raw.get(key, 0.0)) for key in keys}


def _address_from_dict(data: dict[str, Any]) -> RawAddress:
    return RawAddress(
        raw_text=data.get("raw_text") or "",
        street=data.get("street"),
        postal_code=data.get("postal_code"),
        city=data.get("city"),
        country=data.get("country"),
        confidence=_confidence_dict(data.get("confidence") or {}, ADDRESS_CONFIDENCE_FIELDS),
    )


def _line_item_from_dict(data: dict[str, Any]) -> RawLineItem:
    return RawLineItem(
        sku=data.get("sku"),
        description=data.get("description"),
        quantity=data.get("quantity"),
        unit_net_price=data.get("unit_net_price"),
        vat_percent=data.get("vat_percent"),
        discount=data.get("discount"),
        source_line_total=data.get("source_line_total"),
        confidence=_confidence_dict(data.get("confidence") or {}, LINE_ITEM_CONFIDENCE_FIELDS),
    )


def _raw_order_from_tool_input(data: dict[str, Any], *, source_image_path: str) -> RawOrder:
    return RawOrder(
        source_image_path=source_image_path,
        order_date=data.get("order_date"),
        external_reference=data.get("external_reference"),
        debtor_company_name=data.get("debtor_company_name"),
        contact_name=data.get("contact_name"),
        alias=data.get("alias"),
        billing_address=_address_from_dict(data.get("billing_address") or {}),
        delivery_address=_address_from_dict(data.get("delivery_address") or {}),
        payment_details=data.get("payment_details"),
        payment_method=data.get("payment_method"),
        payment_status=data.get("payment_status"),
        payment_date=data.get("payment_date"),
        line_items=[_line_item_from_dict(item) for item in data.get("line_items") or []],
        confidence=_confidence_dict(data.get("confidence") or {}, ORDER_LEVEL_CONFIDENCE_FIELDS),
        extraction_source="vision",
    )
