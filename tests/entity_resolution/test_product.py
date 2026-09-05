"""Tests for entity_resolution.product.resolve_product.

Same duck-typed fake style as tests/entity_resolution/test_debtor.py; see
its module docstring. Selectors mirror entity_resolution/config.py's
Product entries, pinned from probes/probe-07-products.txt.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fakturama_automation.entity_resolution import config
from fakturama_automation.entity_resolution.product import resolve_product
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedLineItem


class _FakeControl:
    def __init__(self) -> None:
        self.click_input_calls = 0
        self.set_text_calls: list[str] = []
        self.select_calls: list[str] = []

    def click_input(self) -> None:
        self.click_input_calls += 1

    def set_text(self, text: str) -> None:
        self.set_text_calls.append(text)

    def select(self, text: str) -> None:
        self.select_calls.append(text)

    def capture_as_image(self):
        return _FakeImage()


class _FakeImage:
    def save(self, buffer, format=None) -> None:  # noqa: A002 - matches PIL's Image.save signature
        buffer.write(b"fake-png-bytes")


class _FakeMainWindow:
    def __init__(self, registry: dict[tuple, _FakeControl]) -> None:
        self._registry = registry
        self.click_input_calls: list[tuple] = []

    def children(self, control_type=None, title=None, auto_id=None):
        control = self._registry.get((control_type, title, auto_id))
        return [control] if control is not None else []

    def capture_as_image(self):
        return _FakeImage()

    def rectangle(self):
        return SimpleNamespace(left=100, top=200)

    def click_input(self, coords=None, absolute=None) -> None:
        self.click_input_calls.append((coords, absolute))


class _FakeApp:
    def __init__(self, main_window: _FakeMainWindow) -> None:
        self._main_window = main_window

    def main_window(self):
        return self._main_window


class _FakeMessages:
    def __init__(self, rows: list[dict], combo_options: list[dict] | None = None) -> None:
        self._rows = rows
        self._combo_options = combo_options or []

    def create(self, **kwargs):
        tool_name = kwargs["tool_choice"]["name"]
        if tool_name == "record_combo_options":
            input_data = {"options": self._combo_options}
        else:
            input_data = {"rows": self._rows}
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", name=tool_name, input=input_data)],
        )


class _FakeVisionClient:
    def __init__(self, rows: list[dict], combo_options: list[dict] | None = None) -> None:
        self.messages = _FakeMessages(rows, combo_options)


def _search_registry(nav: _FakeControl, search_edit: _FakeControl, grid_pane: _FakeControl) -> dict:
    return {
        ("Text", "Products", None): nav,
        ("Edit", None, config.PRODUCT_SEARCH_EDIT_AUTO_ID): search_edit,
        ("Pane", None, config.PRODUCT_LIST_PANE_AUTO_ID): grid_pane,
    }


def _golden_item(**overrides) -> NormalizedLineItem:
    defaults = dict(
        sku="ABC-1",
        description="Office chair",
        quantity=Decimal(3),
        unit_net_price=Decimal("150.00"),
        vat_percent=Decimal("19"),
    )
    defaults.update(overrides)
    return NormalizedLineItem(**defaults)


def test_returns_the_existing_product_without_creating_when_exactly_one_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeControl()
    app = _FakeApp(_FakeMainWindow(_search_registry(nav, search_edit, grid_pane)))
    client = _FakeVisionClient(rows=[{"Item Number": "ABC-1"}])

    result = resolve_product(app, _golden_item(), client=client, settle_seconds=0)

    assert result.created is False
    assert result.identity == "ABC-1"
    assert nav.click_input_calls == 1
    assert search_edit.set_text_calls == ["ABC-1"]


def test_creates_a_new_product_and_fills_the_form_when_no_match(monkeypatch) -> None:
    # resolve_product's create() path calls vat_rate.resolve_vat_rate first
    # (product.py: "never skipped"); that's not yet implemented (blocked on
    # a probe gap - see vat_rate.py), so it's stubbed out here to isolate
    # this test to resolve_product's own behavior.
    monkeypatch.setattr(
        "fakturama_automation.entity_resolution.product.resolve_vat_rate",
        lambda app, vat_percent, *, client=None: None,
    )

    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeControl()
    new_button = _FakeControl()
    sku_edit = _FakeControl()
    name_edit = _FakeControl()
    price_edit = _FakeControl()
    vat_combo = _FakeControl()
    save_button = _FakeControl()

    registry = _search_registry(nav, search_edit, grid_pane)
    registry.update(
        {
            ("Button", config.PRODUCT_NEW_BUTTON_TITLE, None): new_button,
            ("Edit", None, config.PRODUCT_FORM_SKU_AUTO_ID): sku_edit,
            ("Edit", None, config.PRODUCT_FORM_NAME_AUTO_ID): name_edit,
            ("Edit", None, config.PRODUCT_FORM_PRICE_AUTO_ID): price_edit,
            ("ComboBox", None, config.PRODUCT_FORM_VAT_COMBO_AUTO_ID): vat_combo,
            ("Button", config.SAVE_BUTTON_TITLE, None): save_button,
        }
    )
    main_window = _FakeMainWindow(registry)
    app = _FakeApp(main_window)
    client = _FakeVisionClient(
        rows=[], combo_options=[{"text": "19 %", "x": 10, "y": 20, "width": 40, "height": 10}]
    )

    result = resolve_product(app, _golden_item(), client=client, settle_seconds=0)

    assert result.created is True
    assert new_button.click_input_calls == 1
    assert sku_edit.set_text_calls == ["ABC-1"]
    assert name_edit.set_text_calls == ["Office chair"]
    assert price_edit.set_text_calls == ["150.00"]
    assert vat_combo.click_input_calls == 1
    assert main_window.click_input_calls == [((100 + 10 + 20, 200 + 20 + 5), True)]
    assert save_button.click_input_calls == 1


def test_raises_manual_review_when_more_than_one_exact_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeControl()
    app = _FakeApp(_FakeMainWindow(_search_registry(nav, search_edit, grid_pane)))
    client = _FakeVisionClient(rows=[{"Item Number": "ABC-1"}, {"Item Number": "ABC-1"}])

    with pytest.raises(ManualReviewRequired) as exc_info:
        resolve_product(app, _golden_item(), client=client, settle_seconds=0)

    assert exc_info.value.step == "resolve_product"
    assert "ABC-1" in exc_info.value.reason
