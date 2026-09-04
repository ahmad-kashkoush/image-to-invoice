"""Typed, validated data models produced by fakturama_automation.normalization.

Section 2 (normalization). These are the shapes ui_automation and
orchestrator should consume; extraction/models.py holds the raw,
pre-validation counterparts.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class NormalizedAddress:
    """A billing or delivery address with plain, trimmed text fields.

    A delivery address may be entirely blank if the source document left
    it empty (see normalizer.py::_normalize_address); that is a
    completeness concern for validators.py::check_required_fields, not
    something this shape enforces itself.
    """

    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = ""


@dataclass
class NormalizedLineItem:
    """One order line item with canonical types: quantity, unit_net_price,
    discount (a plain percentage, e.g. 10 for 10%), and source_line_total
    as rounded Decimal; vat_percent as a plain number (no percent sign).

    recomputed_total is quantity x unit_net_price x (1 - discount / 100)
    (Task rule 3.16 - VAT is not part of the net line total), filled in by
    normalizer.py and checked against source_line_total by
    validators.py::check_line_total.
    """

    sku: str = ""
    description: str = ""
    quantity: Decimal = Decimal(0)
    unit_net_price: Decimal = Decimal(0)
    vat_percent: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)
    source_line_total: Decimal = Decimal(0)
    recomputed_total: Decimal = Decimal(0)


@dataclass
class NormalizedOrder:
    """The full normalized order, ready for entity_resolution and
    ui_automation to consume.

    Must satisfy validators.py::check_required_fields (debtor company name
    present and at least one line item with a SKU and positive quantity)
    before normalizer.py returns it; otherwise normalization fails closed
    with ManualReviewRequired.
    """

    order_date: datetime.date | None = None
    external_reference: str = ""
    debtor_company_name: str = ""
    contact_name: str = ""
    alias: str = ""
    billing_address: NormalizedAddress = field(default_factory=NormalizedAddress)
    delivery_address: NormalizedAddress = field(default_factory=NormalizedAddress)
    payment_method: str = ""
    payment_status: str = ""
    payment_date: datetime.date | None = None
    line_items: list[NormalizedLineItem] = field(default_factory=list)
