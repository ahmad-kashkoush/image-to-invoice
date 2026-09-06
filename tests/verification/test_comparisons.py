"""Tests for verification.comparisons.

Pure, no fakes needed - same style as tests/entity_resolution/test_matching.py.
Uses the golden sample order's numbers (WEB-2026-0714-A17, Northstar Office
GmbH: line 1 CHR-ERG-01 qty 2 @ 250.00, 10% discount, 19% VAT, net 450.00;
line 2 MAT-DESK-02 qty 3 @ 40.00, 0% discount, 19% VAT, net 120.00; totals
net 570.00, VAT 108.30, gross 678.30) so the derived-totals arithmetic is
checked against a known-correct example, not just invariants.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from fakturama_automation.normalization.models import NormalizedLineItem, NormalizedOrder
from fakturama_automation.verification import comparisons

# -- parse_money_text / money_equals -------------------------------------


def test_parse_money_text_handles_dot_decimal() -> None:
    assert comparisons.parse_money_text("450.00") == Decimal("450.00")


def test_parse_money_text_handles_european_comma_decimal() -> None:
    assert comparisons.parse_money_text("1.234,56") == Decimal("1234.56")


def test_parse_money_text_strips_currency_symbols() -> None:
    assert comparisons.parse_money_text("€ 450.00") == Decimal("450.00")


def test_parse_money_text_returns_none_for_unparseable() -> None:
    assert comparisons.parse_money_text("n/a") is None


def test_parse_money_text_returns_none_for_blank() -> None:
    assert comparisons.parse_money_text("   ") is None


def test_money_equals_true_within_tolerance() -> None:
    assert comparisons.money_equals(Decimal("450.00"), "450.00")
    assert comparisons.money_equals(Decimal("450.00"), "450.005")


def test_money_equals_false_when_mismatched() -> None:
    assert not comparisons.money_equals(Decimal("450.00"), "449.00")


def test_money_equals_false_when_unparseable() -> None:
    assert not comparisons.money_equals(Decimal("450.00"), "garbled")


# -- percent_equals --------------------------------------------------------


def test_percent_equals_true_for_plain_number() -> None:
    assert comparisons.percent_equals(Decimal("19"), "19")


def test_percent_equals_true_for_percent_sign_and_comma_decimal() -> None:
    assert comparisons.percent_equals(Decimal("19"), "19,00 %")


def test_percent_equals_false_for_different_rate() -> None:
    assert not comparisons.percent_equals(Decimal("19"), "7")


def test_percent_equals_false_when_unparseable() -> None:
    assert not comparisons.percent_equals(Decimal("19"), "n/a")


# -- text_equals ------------------------------------------------------------


def test_text_equals_trims_whitespace() -> None:
    assert comparisons.text_equals("Northstar Office GmbH", "  Northstar Office GmbH  ")


def test_text_equals_is_case_sensitive() -> None:
    assert not comparisons.text_equals("Northstar Office GmbH", "northstar office gmbh")


# -- parse_ui_date / date_equals --------------------------------------------


def test_parse_ui_date_accepts_iso() -> None:
    assert comparisons.parse_ui_date("2026-07-18") == datetime.date(2026, 7, 18)


def test_parse_ui_date_accepts_day_first_fallback() -> None:
    assert comparisons.parse_ui_date("18.07.2026") == datetime.date(2026, 7, 18)


def test_parse_ui_date_rejects_ambiguous_slash_date() -> None:
    assert comparisons.parse_ui_date("07/18/2026") is None


def test_date_equals_true_for_matching_date() -> None:
    assert comparisons.date_equals(datetime.date(2026, 7, 18), "2026-07-18")


def test_date_equals_false_for_mismatched_date() -> None:
    assert not comparisons.date_equals(datetime.date(2026, 7, 18), "2026-07-19")


def test_date_equals_true_when_none_expected_and_ui_blank() -> None:
    assert comparisons.date_equals(None, "")


def test_date_equals_false_when_none_expected_but_ui_has_a_date() -> None:
    assert not comparisons.date_equals(None, "2026-07-18")


# -- order_level_totals (golden sample order) -------------------------------


def _golden_line_items() -> list[NormalizedLineItem]:
    line1 = NormalizedLineItem(
        sku="CHR-ERG-01",
        description="Ergonomic Desk Chair",
        quantity=Decimal("2"),
        unit_net_price=Decimal("250.00"),
        vat_percent=Decimal("19"),
        discount=Decimal("10"),
        source_line_total=Decimal("450.00"),
    )
    line2 = NormalizedLineItem(
        sku="MAT-DESK-02",
        description="Anti-Fatigue Desk Mat",
        quantity=Decimal("3"),
        unit_net_price=Decimal("40.00"),
        vat_percent=Decimal("19"),
        discount=Decimal("0"),
        source_line_total=Decimal("120.00"),
    )
    return [line1, line2]


def test_order_level_totals_matches_golden_sample_order() -> None:
    order = NormalizedOrder(line_items=_golden_line_items())

    net_total, vat_total, gross_total = comparisons.order_level_totals(order)

    assert net_total == Decimal("570.00")
    assert vat_total == Decimal("108.30")
    assert gross_total == Decimal("678.30")


# -- line_row_problems -------------------------------------------------------


def _golden_row(**overrides) -> dict[str, str]:
    row = {
        "SKU": "CHR-ERG-01",
        "Qty.": "2",
        "U.Price": "250.00",
        "VAT": "19",
        "Discount": "10",
        "Price": "450.00",
    }
    row.update(overrides)
    return row


def test_line_row_problems_empty_when_row_matches() -> None:
    item = _golden_line_items()[0]

    assert comparisons.line_row_problems(item, _golden_row()) == []


def test_line_row_problems_reports_sku_mismatch() -> None:
    item = _golden_line_items()[0]

    problems = comparisons.line_row_problems(item, _golden_row(SKU="WRONG-SKU"))

    assert len(problems) == 1
    assert "SKU" in problems[0]


def test_line_row_problems_reports_every_mismatched_field() -> None:
    item = _golden_line_items()[0]

    problems = comparisons.line_row_problems(
        item, _golden_row(**{"Qty.": "9", "U.Price": "1.00", "VAT": "7", "Discount": "0", "Price": "1.00"})
    )

    assert len(problems) == 5
