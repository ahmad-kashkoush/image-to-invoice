from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from fakturama_automation.normalization.config import MONEY_QUANTIZE

_HUNDRED = Decimal(100)

# case-insensitively against the extracted, trimmed status text.
PAID_STATUS = "PAID"


@dataclass
class NormalizedAddress:
    # May be entirely blank; completeness is check_required_fields' concern.
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = ""


@dataclass
class NormalizedLineItem:
    sku: str = ""
    description: str = ""
    quantity: Decimal = Decimal(0)
    unit_net_price: Decimal = Decimal(0)
    vat_percent: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)
    source_line_total: Decimal = Decimal(0)

    @property
    def recomputed_total(self) -> Decimal:
        total = self.quantity * self.unit_net_price * (Decimal(1) - self.discount / _HUNDRED)
        return total.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


@dataclass
class NormalizedOrder:
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
        return self.payment_status.strip().upper() == PAID_STATUS
