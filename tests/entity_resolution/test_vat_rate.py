"""Tests for entity_resolution.vat_rate.resolve_vat_rate.

resolve_vat_rate is intentionally still a stub: probes/probe-08-vats.txt
did not capture the VATs list or its create form (a probe gap, not a
design gap - see vat_rate.py's module docstring and
.claude/plans/entity-resolution.md's "Remaining probe gap"). This test
only pins down that the stub fails loudly with a message pointing at the
gap, rather than silently returning None or guessing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fakturama_automation.entity_resolution.vat_rate import resolve_vat_rate


def test_raises_not_implemented_naming_the_probe_gap() -> None:
    with pytest.raises(NotImplementedError, match="VATs list/create-form probe"):
        resolve_vat_rate(app=object(), vat_percent=Decimal("19"))
