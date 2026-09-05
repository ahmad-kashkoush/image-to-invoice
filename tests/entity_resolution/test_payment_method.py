"""Tests for entity_resolution.payment_method.resolve_payment_method.

Same duck-typed fake style as tests/entity_resolution/test_debtor.py; see
its module docstring. Selectors mirror entity_resolution/config.py's
Payment entries, pinned from probes/probe-09-Payment.txt (search) and
probes/probe-10-payment-create-form.txt (create form).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fakturama_automation.entity_resolution import config
from fakturama_automation.entity_resolution.payment_method import resolve_payment_method
from fakturama_automation.error_handling.exceptions import ManualReviewRequired


class _FakeControl:
    def __init__(self) -> None:
        self.click_input_calls = 0
        self.set_text_calls: list[str] = []

    def click_input(self) -> None:
        self.click_input_calls += 1

    def set_text(self, text: str) -> None:
        self.set_text_calls.append(text)


class _FakeImage:
    def save(self, buffer, format=None) -> None:  # noqa: A002 - matches PIL's Image.save signature
        buffer.write(b"fake-png-bytes")


class _FakeGridPane(_FakeControl):
    def capture_as_image(self):
        return _FakeImage()


class _FakeMainWindow:
    def __init__(self, registry: dict[tuple, _FakeControl]) -> None:
        self._registry = registry

    def descendants(self, control_type=None, title=None, auto_id=None):
        control = self._registry.get((control_type, title, auto_id))
        return [control] if control is not None else []


class _FakeApp:
    def __init__(self, main_window: _FakeMainWindow) -> None:
        self._main_window = main_window

    def main_window(self):
        return self._main_window


class _FakeMessages:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def create(self, **kwargs):
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", name="record_grid_rows", input={"rows": self._rows})],
        )


class _FakeVisionClient:
    def __init__(self, rows: list[dict]) -> None:
        self.messages = _FakeMessages(rows)


def _search_registry(nav: _FakeControl, search_edit: _FakeControl, grid_pane: _FakeGridPane) -> dict:
    return {
        ("Text", "terms of payment", None): nav,
        ("Edit", None, config.PAYMENT_SEARCH_EDIT_AUTO_ID): search_edit,
        ("Pane", None, config.PAYMENT_LIST_PANE_AUTO_ID): grid_pane,
    }


def test_returns_the_existing_payment_method_without_creating_when_exactly_one_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeGridPane()
    app = _FakeApp(_FakeMainWindow(_search_registry(nav, search_edit, grid_pane)))
    client = _FakeVisionClient(rows=[{"Name": "Cash"}])

    result = resolve_payment_method(app, "Cash", client=client, settle_seconds=0)

    assert result.created is False
    assert result.identity == "Cash"
    assert nav.click_input_calls == 1
    assert search_edit.set_text_calls == ["Cash"]


def test_raises_manual_review_when_more_than_one_exact_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeGridPane()
    app = _FakeApp(_FakeMainWindow(_search_registry(nav, search_edit, grid_pane)))
    client = _FakeVisionClient(rows=[{"Name": "Cash"}, {"Name": "Cash"}])

    with pytest.raises(ManualReviewRequired) as exc_info:
        resolve_payment_method(app, "Cash", client=client, settle_seconds=0)

    assert exc_info.value.step == "resolve_payment_method"


def test_creates_a_new_payment_method_and_fills_the_form_when_no_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeGridPane()
    new_button = _FakeControl()
    name_edit = _FakeControl()
    save_button = _FakeControl()

    registry = _search_registry(nav, search_edit, grid_pane)
    registry.update(
        {
            ("Button", config.PAYMENT_NEW_BUTTON_TITLE, None): new_button,
            ("Edit", None, config.PAYMENT_FORM_NAME_AUTO_ID): name_edit,
            ("Button", config.SAVE_BUTTON_TITLE, None): save_button,
        }
    )
    app = _FakeApp(_FakeMainWindow(registry))
    client = _FakeVisionClient(rows=[])

    result = resolve_payment_method(app, "Bank Transfer", client=client, settle_seconds=0)

    assert result.created is True
    assert result.identity == "Bank Transfer"
    assert new_button.click_input_calls == 1
    assert name_edit.set_text_calls == ["Bank Transfer"]
    assert save_button.click_input_calls == 1
