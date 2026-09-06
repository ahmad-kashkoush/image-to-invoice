"""Pure exact-match filtering over rows read back from Fakturama.

Fakturama's list/search result grids are custom-rendered and don't expose
per-row elements to UIA, so each resolver reads the grid back via
ui_automation.vision_grounding.read_grid_rows as plain column-name -> text
dicts; the *filtering* of those rows down to an exact match is pure and
lives here, independent of how the rows were obtained.

Exact match only, never fuzzy (Doc/Design.md's Tradeoffs section): a
near-miss is treated as "no match" and routed to creation/manual review by
resolver.py, never silently matched to the wrong record.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from fakturama_automation.normalization.parsing import parse_percent_text


def _default_read(row: Any) -> str:
    """Default row -> text accessor: read_grid_rows rows are plain dicts,
    but this also accepts anything exposing window_text() (a live pywinauto
    element), so a caller can pass real controls through unchanged in the
    rare case a row *is* individually addressable.
    """
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
    """Return every row whose text equals target exactly (case-sensitive).

    Used for debtor company name, product SKU, and payment method name -
    all already trimmed by normalization, so strict equality is the
    fail-closed choice: it never assumes "close enough" is the same
    record.
    """
    return [row for row in rows if read(row) == target]


def exact_vat_matches(
    rows: list[Any],
    vat_percent: Decimal,
    *,
    read: Callable[[Any], str] = _default_read,
) -> list[Any]:
    """Return every row whose VAT percent, parsed from its text, equals
    vat_percent numerically (so "19", "19.00", and "19,00 %" all match a
    target of Decimal("19")).

    A row whose text does not parse as a number is not a match (excluded,
    not raised) - an unparseable row is not evidence of an exact match,
    and resolve_exact_or_create's zero/one/many counting still fails
    closed on whatever remains.
    """
    matches = []
    for row in rows:
        parsed = parse_percent_text(read(row))
        if parsed is not None and parsed == vat_percent:
            matches.append(row)
    return matches
