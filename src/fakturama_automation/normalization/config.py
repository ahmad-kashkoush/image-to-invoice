"""Configuration for normalization and validation."""

from __future__ import annotations

import os
from decimal import Decimal

# A field the vision pass reports below this is treated as unreliable and
# fails the order closed rather than being silently trusted.
DEFAULT_CONFIDENCE_THRESHOLD = float(
    os.environ.get("FAKTURAMA_NORMALIZATION_CONFIDENCE_THRESHOLD", "0.75")
)

# Allowed drift between a recomputed line total and the source line total
# before check_line_total treats it as a mismatch (e.g. source rounding).
DEFAULT_LINE_TOTAL_TOLERANCE = Decimal(
    os.environ.get("FAKTURAMA_NORMALIZATION_LINE_TOTAL_TOLERANCE", "0.01")
)

# All monetary values are quantized to 2 decimal places, half-up, matching
# Fakturama's own money field precision.
MONEY_QUANTIZE = Decimal("0.01")
