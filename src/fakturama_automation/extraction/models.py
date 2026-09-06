"""Raw data models produced by extraction, before fakturama_automation.normalization.

Fields here are intentionally loose (mostly str) because they come straight
off a vision LLM or OCR pass and have not been typed, rounded, or validated
yet. See normalization/models.py for the typed, validated counterparts.

Confidence keying convention (relied on by
normalization.validators.check_confidence):
  - RawOrder.confidence holds only RawOrder's own scalar fields (order_date,
    external_reference, debtor_company_name, contact_name, alias,
    payment_details, payment_method, payment_status, payment_date).
  - RawAddress.confidence and RawLineItem.confidence hold their own fields,
    keyed by field name, on their own objects (billing_address, delivery_address,
    each item in line_items) rather than as dotted paths in RawOrder.confidence.
  - A missing key means "not extracted" and must be treated as 0.0 (fail
    closed) by any downstream reader, never as high confidence.

Confidence itself is a heuristic, not a calibrated probability: it is
self-reported by the vision LLM and is at best weakly correlated with true
legibility. It is used only to decide what would need a closer look (e.g. an
OCR fallback pass), never as proof that a value is correct. The actual
correctness gate for line items is the deterministic recomputation in
normalization/validators.py::check_line_total.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Which fields each raw model carries a confidence for. Here rather than in
# vision_extractor.py because they describe these shapes, not the API call
# that happens to fill them - and because validators.check_confidence reads
# them, which would otherwise pull the Anthropic SDK into the import chain
# of every module that validates an order.
ADDRESS_CONFIDENCE_FIELDS = ["street", "postal_code", "city", "country"]
LINE_ITEM_CONFIDENCE_FIELDS = [
    "sku",
    "description",
    "quantity",
    "unit_net_price",
    "vat_percent",
    "discount",
    "source_line_total",
]
ORDER_LEVEL_CONFIDENCE_FIELDS = [
    "order_date",
    "external_reference",
    "debtor_company_name",
    "contact_name",
    "alias",
    "payment_details",
    "payment_method",
    "payment_status",
    "payment_date",
]


@dataclass
class RawAddress:
    """A single billing or delivery address as read from the image."""

    raw_text: str = ""
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    confidence: dict[str, float] = field(default_factory=dict)


@dataclass
class RawLineItem:
    """One order line item as read from the image."""

    sku: str | None = None
    description: str | None = None
    quantity: str | None = None
    unit_net_price: str | None = None
    vat_percent: str | None = None
    discount: str | None = None
    source_line_total: str | None = None
    confidence: dict[str, float] = field(default_factory=dict)


@dataclass
class RawOrder:
    """The full raw extraction result for a single order image."""

    source_image_path: str = ""
    order_date: str | None = None
    external_reference: str | None = None
    debtor_company_name: str | None = None
    contact_name: str | None = None
    alias: str | None = None
    billing_address: RawAddress = field(default_factory=RawAddress)
    delivery_address: RawAddress = field(default_factory=RawAddress)
    payment_details: str | None = None
    payment_method: str | None = None
    payment_status: str | None = None
    payment_date: str | None = None
    line_items: list[RawLineItem] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
    extraction_source: str = "vision"
