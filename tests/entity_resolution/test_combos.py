"""Tests for entity_resolution.combos.

Same duck-typed fake style as tests/entity_resolution/test_debtor.py /
test_product.py; see their module docstrings. The vision client is a fake
exposing just `.messages.create(...)`, returning a record_combo_options
tool call - no real screenshot, no network.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fakturama_automation.entity_resolution.combos import pick_option, select_exact_option, select_vat_option
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation.vision_grounding import ComboOption


class _FakeCombo:
    def __init__(self) -> None:
        self.click_input_calls = 0

    def click_input(self) -> None:
        self.click_input_calls += 1


class _FakeImage:
    def save(self, buffer, format=None) -> None:  # noqa: A002 - matches PIL's Image.save signature
        buffer.write(b"fake-png-bytes")


class _FakeMainWindow:
    def __init__(self, *, left: int = 100, top: int = 200) -> None:
        self._left = left
        self._top = top
        self.click_input_calls: list[tuple] = []

    def capture_as_image(self):
        return _FakeImage()

    def rectangle(self):
        return SimpleNamespace(left=self._left, top=self._top)

    def click_input(self, coords=None, absolute=None) -> None:
        self.click_input_calls.append((coords, absolute))


class _FakeMessages:
    def __init__(self, options: list[dict]) -> None:
        self._options = options

    def create(self, **kwargs):
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", name="record_combo_options", input={"options": self._options})],
        )


class _FakeVisionClient:
    def __init__(self, options: list[dict]) -> None:
        self.messages = _FakeMessages(options)


# -- pick_option (pure) ------------------------------------------------


def test_pick_option_returns_the_single_match() -> None:
    options = [ComboOption(text="19 %", bbox=(0, 0, 10, 10)), ComboOption(text="7 %", bbox=(0, 20, 10, 10))]

    assert pick_option(options, match=lambda text: text == "19 %") is options[0]


def test_pick_option_returns_none_on_zero_matches() -> None:
    options = [ComboOption(text="19 %", bbox=(0, 0, 10, 10))]

    assert pick_option(options, match=lambda text: text == "7 %") is None


def test_pick_option_returns_none_on_ambiguous_matches() -> None:
    options = [ComboOption(text="19 %", bbox=(0, 0, 10, 10)), ComboOption(text="19 %", bbox=(0, 20, 10, 10))]

    assert pick_option(options, match=lambda text: text == "19 %") is None


# -- select_vat_option ---------------------------------------------------


def test_select_vat_option_opens_combo_and_clicks_the_matched_option() -> None:
    combo = _FakeCombo()
    main_window = _FakeMainWindow(left=100, top=200)
    client = _FakeVisionClient(options=[{"text": "19 %", "x": 10, "y": 30, "width": 50, "height": 20}])

    select_vat_option(main_window, combo, Decimal("19"), client=client, step="resolve_product")

    assert combo.click_input_calls == 1
    assert main_window.click_input_calls == [((100 + 10 + 25, 200 + 30 + 10), True)]


def test_select_vat_option_raises_manual_review_when_no_option_matches() -> None:
    combo = _FakeCombo()
    main_window = _FakeMainWindow()
    client = _FakeVisionClient(options=[{"text": "7 %", "x": 0, "y": 0, "width": 10, "height": 10}])

    with pytest.raises(ManualReviewRequired) as exc_info:
        select_vat_option(main_window, combo, Decimal("19"), client=client, step="resolve_product")

    assert exc_info.value.step == "resolve_product"
    assert "7 %" in exc_info.value.reason
    assert main_window.click_input_calls == []


def test_select_vat_option_raises_manual_review_when_more_than_one_option_matches() -> None:
    combo = _FakeCombo()
    main_window = _FakeMainWindow()
    client = _FakeVisionClient(
        options=[
            {"text": "19 %", "x": 0, "y": 0, "width": 10, "height": 10},
            {"text": "19,00 %", "x": 0, "y": 20, "width": 10, "height": 10},
        ]
    )

    with pytest.raises(ManualReviewRequired) as exc_info:
        select_vat_option(main_window, combo, Decimal("19"), client=client, step="resolve_product")

    assert exc_info.value.step == "resolve_product"
    assert main_window.click_input_calls == []


# -- select_exact_option --------------------------------------------------


def test_select_exact_option_opens_combo_and_clicks_the_matched_option() -> None:
    combo = _FakeCombo()
    main_window = _FakeMainWindow(left=100, top=200)
    client = _FakeVisionClient(options=[{"text": "Germany", "x": 5, "y": 15, "width": 40, "height": 10}])

    select_exact_option(main_window, combo, "Germany", client=client, step="resolve_debtor")

    assert combo.click_input_calls == 1
    assert main_window.click_input_calls == [((100 + 5 + 20, 200 + 15 + 5), True)]


def test_select_exact_option_raises_manual_review_when_no_option_matches() -> None:
    # e.g. normalized data holds a country code ("DE") but the combo's
    # real options are full country names - a mismatch, not a fuzzy match.
    combo = _FakeCombo()
    main_window = _FakeMainWindow()
    client = _FakeVisionClient(options=[{"text": "Germany", "x": 0, "y": 0, "width": 10, "height": 10}])

    with pytest.raises(ManualReviewRequired) as exc_info:
        select_exact_option(main_window, combo, "DE", client=client, step="resolve_debtor")

    assert exc_info.value.step == "resolve_debtor"
    assert "Germany" in exc_info.value.reason
    assert main_window.click_input_calls == []


def test_select_exact_option_raises_manual_review_when_more_than_one_option_matches() -> None:
    combo = _FakeCombo()
    main_window = _FakeMainWindow()
    client = _FakeVisionClient(
        options=[
            {"text": "Germany", "x": 0, "y": 0, "width": 10, "height": 10},
            {"text": "Germany", "x": 0, "y": 20, "width": 10, "height": 10},
        ]
    )

    with pytest.raises(ManualReviewRequired) as exc_info:
        select_exact_option(main_window, combo, "Germany", client=client, step="resolve_debtor")

    assert exc_info.value.step == "resolve_debtor"
    assert main_window.click_input_calls == []
