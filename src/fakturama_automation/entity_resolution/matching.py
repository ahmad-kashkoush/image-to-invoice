"""Pure exact-match filtering over rows read back from Fakturama.

Section 4 (entity_resolution). Fakturama's list/search result grids are
custom-rendered (SWT/NatTable) and do not expose per-row elements to UIA
(confirmed against probes/probe-06-debitors.txt, probe-07-products.txt,
probe-09-Payment.txt: each results pane has no child controls). So each
resolver's search step reads the filtered grid back via
ui_automation.vision_grounding.read_grid_rows, which returns rows as plain
dicts of column-name -> text; the *filtering* of those rows down to an
exact match is pure and lives here, independent of how the rows were
obtained, so it can be unit-tested without a screenshot or a live window.

Exact match only, never fuzzy (Doc/Design.md's Tradeoffs section): a
near-miss (extra whitespace already handled by normalization, a
differently-cased name, a rounding-different VAT percent) is treated as
"no match" and routed to creation/manual review by resolver.py, never
silently matched to the wrong record.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

# Mirrors normalization.normalizer's locale-tolerant number parsing (dot or
# European comma decimal, optional thousands separator, optional currency/
# percent symbol) so a VAT rate read back from the UI ("19 %", "19,00 %")
# compares equal to the Decimal produced by normalization.
_PERCENT_SYMBOL = re.compile(r"%")


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
        parsed = parse_vat_text(read(row))
        if parsed is not None and parsed == vat_percent:
            matches.append(row)
    return matches


def parse_vat_text(text: str) -> Decimal | None:
    """Parse a VAT percent read back from Fakturama's UI ("19 %",
    "19,00 %", a bare "19") to a Decimal, or None if it doesn't parse.

    Public (not module-private) so other modules needing the same
    VAT-text parsing (e.g. a future ComboBox-option reader) reuse this one
    implementation rather than re-deriving it - CLAUDE.md's "keep this
    formula in exactly one place" rule applied to VAT-text parsing, not
    just the line total formula.
    """
    cleaned = _PERCENT_SYMBOL.sub("", text).strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
