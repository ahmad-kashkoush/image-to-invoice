"""Typed, validated data models produced by fakturama_automation.normalization.

These are the shapes ui_automation and orchestrator consume;
extraction/models.py holds the raw, pre-validation counterparts.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from fakturama_automation.normalization.config import MONEY_QUANTIZE

_HUNDRED = Decimal(100)

# The one payment status meaning the invoice has been paid, compared
# case-insensitively against the extracted, trimmed status text.
PAID_STATUS = "PAID"


@dataclass
class NormalizedAddress:
    """A billing or delivery address with plain, trimmed text fields.

    May be entirely blank if the source document left it empty; that is a
    completeness concern for validators.check_required_fields, not something
    this shape enforces.
    """

    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = ""


@dataclass
class NormalizedLineItem:
    """One order line item with canonical types: quantity, unit_net_price,
    discount (a plain percentage, e.g. 10 for 10%) and source_line_total as
    rounded Decimal; vat_percent as a plain number.
    """

    sku: str = ""
    description: str = ""
    quantity: Decimal = Decimal(0)
    unit_net_price: Decimal = Decimal(0)
    vat_percent: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)
    source_line_total: Decimal = Decimal(0)

    @property
    def recomputed_total(self) -> Decimal:
        """Net total per Task rule 3.16: quantity x unit net price x
        (1 - discount / 100), 2 places, half-up. VAT is not part of it.

        The single home of that formula - validators.recompute_line_total
        delegates here. A property rather than a field the normalizer fills
        in afterwards because every order-level total in the system derives
        from it, including the payment Value written into Fakturama: a line
        item built any other way used to contribute 0.00 silently.
        """
        total = self.quantity * self.unit_net_price * (Decimal(1) - self.discount / _HUNDRED)
        return total.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


@dataclass
class NormalizedOrder:
    """The full normalized order, ready for entity_resolution and
    ui_automation to consume.

    Must satisfy validators.check_required_fields before normalizer.py
    returns it; otherwise normalization fails closed.
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

    @property
    def is_paid(self) -> bool:
        """Whether the extracted status means PAID.

        The single interpretation of that string: the step that writes
        payment and the read-back that verifies it must agree exactly, and
        used to hold separate copies of the comparison.
        """
        return self.payment_status.strip().upper() == PAID_STATUS
