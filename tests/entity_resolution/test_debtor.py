"""Tests for entity_resolution.debtor.resolve_debtor.

Duck-typed fakes for the pywinauto app/window/control objects (same style
as tests/ui_automation/test_controls.py) and a fake anthropic-compatible
vision client (same style as tests/extraction/test_vision_extractor.py) -
no real window, no screenshot, no network. Each fake control is looked up
by the exact (control_type, title, auto_id) triple resolve_debtor's
find_control calls use, mirroring the selectors pinned in
entity_resolution/config.py from probes/probe-06-debitors.txt and
probes/probe-03/04-*-debitor.txt.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fakturama_automation.entity_resolution import config
from fakturama_automation.entity_resolution.debtor import resolve_debtor
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedAddress, NormalizedOrder


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
    """children() looks a control up by the exact
    (control_type, title, auto_id) triple find_control passes through -
    good enough to drive resolve_debtor's whole sequence without a real
    window.
    """

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
        ("Text", "Debtors", None): nav,
        ("Edit", None, config.DEBTOR_SEARCH_EDIT_AUTO_ID): search_edit,
        ("Pane", None, config.DEBTOR_LIST_PANE_AUTO_ID): grid_pane,
    }


def _golden_order(**overrides) -> NormalizedOrder:
    defaults = dict(
        debtor_company_name="Northstar Office GmbH",
        contact_name="Jane Doe",
        alias="Northstar",
        billing_address=NormalizedAddress(street="Main St 1", postal_code="10553", city="Berlin", country="Germany"),
    )
    defaults.update(overrides)
    return NormalizedOrder(**defaults)


def test_returns_the_existing_debtor_without_creating_when_exactly_one_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeControl()
    registry = _search_registry(nav, search_edit, grid_pane)
    app = _FakeApp(_FakeMainWindow(registry))
    client = _FakeVisionClient(rows=[{"Company Name": "Northstar Office GmbH"}])

    result = resolve_debtor(app, _golden_order(), client=client, settle_seconds=0)

    assert result.created is False
    assert result.identity == "Northstar Office GmbH"
    assert nav.click_input_calls == 1
    assert search_edit.set_text_calls == ["Northstar Office GmbH"]


def test_creates_a_new_debtor_and_fills_the_form_when_no_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeControl()
    new_button = _FakeControl()
    company_edit = _FakeControl()
    first_name_edit = _FakeControl()
    last_name_edit = _FakeControl()
    alias_edit = _FakeControl()
    street_edit = _FakeControl()
    zip_edit = _FakeControl()
    city_edit = _FakeControl()
    country_combo = _FakeControl()
    save_button = _FakeControl()

    registry = _search_registry(nav, search_edit, grid_pane)
    registry.update(
        {
            ("Button", config.DEBTOR_NEW_BUTTON_TITLE, None): new_button,
            ("Edit", None, config.DEBTOR_FORM_COMPANY_AUTO_ID): company_edit,
            ("Edit", None, config.DEBTOR_FORM_FIRST_NAME_AUTO_ID): first_name_edit,
            ("Edit", None, config.DEBTOR_FORM_LAST_NAME_AUTO_ID): last_name_edit,
            ("Edit", None, config.DEBTOR_FORM_ALIAS_AUTO_ID): alias_edit,
            ("Edit", None, config.DEBTOR_FORM_STREET_AUTO_ID): street_edit,
            ("Edit", None, config.DEBTOR_FORM_ZIP_AUTO_ID): zip_edit,
            ("Edit", None, config.DEBTOR_FORM_CITY_AUTO_ID): city_edit,
            ("ComboBox", None, config.DEBTOR_FORM_COUNTRY_COMBO_AUTO_ID): country_combo,
            ("Button", config.SAVE_BUTTON_TITLE, None): save_button,
        }
    )
    main_window = _FakeMainWindow(registry)
    app = _FakeApp(main_window)
    client = _FakeVisionClient(
        rows=[], combo_options=[{"text": "Germany", "x": 5, "y": 15, "width": 40, "height": 10}]
    )

    result = resolve_debtor(app, _golden_order(), client=client, settle_seconds=0)

    assert result.created is True
    assert new_button.click_input_calls == 1
    assert company_edit.set_text_calls == ["Northstar Office GmbH"]
    assert first_name_edit.set_text_calls == ["Jane"]
    assert last_name_edit.set_text_calls == ["Doe"]
    assert alias_edit.set_text_calls == ["Northstar"]
    assert street_edit.set_text_calls == ["Main St 1"]
    assert zip_edit.set_text_calls == ["10553"]
    assert city_edit.set_text_calls == ["Berlin"]
    assert country_combo.click_input_calls == 1
    assert main_window.click_input_calls == [((100 + 5 + 20, 200 + 15 + 5), True)]
    assert save_button.click_input_calls == 1


def test_raises_manual_review_when_more_than_one_exact_match() -> None:
    nav, search_edit, grid_pane = _FakeControl(), _FakeControl(), _FakeControl()
    app = _FakeApp(_FakeMainWindow(_search_registry(nav, search_edit, grid_pane)))
    client = _FakeVisionClient(
        rows=[{"Company Name": "Northstar Office GmbH"}, {"Company Name": "Northstar Office GmbH"}]
    )

    with pytest.raises(ManualReviewRequired) as exc_info:
        resolve_debtor(app, _golden_order(), client=client, settle_seconds=0)

    assert exc_info.value.step == "resolve_debtor"
    assert "Northstar Office GmbH" in exc_info.value.reason
