from __future__ import annotations

from dataclasses import dataclass, field
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
    raw_text: str = ""
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    confidence: dict[str, float] = field(default_factory=dict)


@dataclass
class RawLineItem:
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
