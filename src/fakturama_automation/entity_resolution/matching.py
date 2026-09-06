from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from fakturama_automation.normalization.parsing import parse_percent_text


def _default_read(row: Any) -> str:
    # read_grid_rows returns plain dicts, but window_text() is accepted too so
    if isinstance(row, dict):
        return str(row.get("text", ""))
    if hasattr(row, "window_text"):
        return str(row.window_text())
    return str(row)


def exact_text_matches(
    rows: list[Any],
    target: str,
    *,
    read: Callable[[Any], str] = _default_read,
) -> list[Any]:
    # Inputs are already trimmed by normalization, so strict equality is the
    return [row for row in rows if read(row) == target]


def exact_vat_matches(
    rows: list[Any],
    vat_percent: Decimal,
    *,
    read: Callable[[Any], str] = _default_read,
) -> list[Any]:
    # Compared numerically, so "19", "19.00" and "19,00 %" all match Decimal(19).
    # A row that does not parse is excluded rather than raising - it is not
    # evidence of a match, and the zero/one/many counting still fails closed.
    matches = []
    for row in rows:
        parsed = parse_percent_text(read(row))
        if parsed is not None and parsed == vat_percent:
            matches.append(row)
    return matches
