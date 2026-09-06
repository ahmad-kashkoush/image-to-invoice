from __future__ import annotations

from decimal import Decimal

from fakturama_automation.entity_resolution.matching import exact_text_matches, exact_vat_matches


def _rows(*texts: str) -> list[dict]:
    return [{"text": text} for text in texts]


# -- exact_text_matches ---------------------------------------------------


def test_exact_text_matches_returns_the_single_exact_row() -> None:
    rows = _rows("Acme GmbH", "Acme Corp", "Northstar Office GmbH")
    matches = exact_text_matches(rows, "Northstar Office GmbH")
    assert matches == [{"text": "Northstar Office GmbH"}]


def test_exact_text_matches_excludes_near_misses() -> None:
    # Case difference and trailing punctuation are deliberately NOT matched:
    # exact match only, per Doc/Design.md's Tradeoffs section.
    rows = _rows("acme gmbh", "Acme Gmbh.", "Acme GmbH ")
    assert exact_text_matches(rows, "Acme GmbH") == []


def test_exact_text_matches_returns_empty_list_for_no_rows() -> None:
    assert exact_text_matches([], "anything") == []


def test_exact_text_matches_returns_every_row_when_ambiguous() -> None:
    rows = _rows("SKU-1", "SKU-1")
    assert exact_text_matches(rows, "SKU-1") == rows


def test_exact_text_matches_uses_custom_read_accessor() -> None:
    rows = [{"company_name": "Acme GmbH"}, {"company_name": "Other"}]
    matches = exact_text_matches(rows, "Acme GmbH", read=lambda row: row["company_name"])
    assert matches == [{"company_name": "Acme GmbH"}]


# -- exact_vat_matches ------------------------------------------------------


def test_exact_vat_matches_plain_number() -> None:
    rows = _rows("19", "7")
    assert exact_vat_matches(rows, Decimal("19")) == [{"text": "19"}]


def test_exact_vat_matches_percent_sign_and_whitespace() -> None:
    rows = _rows("19 %", "7 %")
    assert exact_vat_matches(rows, Decimal("19")) == [{"text": "19 %"}]


def test_exact_vat_matches_european_comma_decimal() -> None:
    rows = _rows("19,00 %")
    assert exact_vat_matches(rows, Decimal("19")) == rows


def test_exact_vat_matches_treats_unparseable_row_as_no_match() -> None:
    rows = _rows("n/a", "19")
    assert exact_vat_matches(rows, Decimal("19")) == [{"text": "19"}]


def test_exact_vat_matches_returns_empty_list_for_no_rows() -> None:
    assert exact_vat_matches([], Decimal("19")) == []


def test_exact_vat_matches_does_not_match_a_different_rate() -> None:
    rows = _rows("7 %")
    assert exact_vat_matches(rows, Decimal("19")) == []
