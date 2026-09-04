"""Tests for entity_resolution.resolver.

resolve_exact_or_create's tests are pure function tests - search_by/create
are plain callables, no UI, no network. See
tests/normalization/test_normalizer.py for the equivalent pattern of
asserting on a raised ManualReviewRequired's message.

search_grid_exact's tests use duck-typed fakes for the pywinauto
parent/edit/grid-pane objects (same style as
tests/ui_automation/test_controls.py) and a fake anthropic-compatible
vision client (same style as tests/extraction/test_vision_extractor.py) -
no real window, no screenshot, no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fakturama_automation.entity_resolution.resolver import resolve_exact_or_create, search_grid_exact
from fakturama_automation.error_handling.exceptions import ManualReviewRequired


def test_returns_the_single_exact_match_without_creating() -> None:
    created = {"called": False}

    def search_by():
        return ["existing-record"]

    def create():
        created["called"] = True
        return "new-record"

    result = resolve_exact_or_create(search_by, create)

    assert result == "existing-record"
    assert created["called"] is False


def test_creates_when_no_match_found() -> None:
    def search_by():
        return []

    def create():
        return "new-record"

    result = resolve_exact_or_create(search_by, create)

    assert result == "new-record"


def test_raises_manual_review_when_more_than_one_match() -> None:
    def search_by():
        return ["record-a", "record-b"]

    def create():
        raise AssertionError("create() must not be called when matches are ambiguous")

    with pytest.raises(ManualReviewRequired) as exc_info:
        resolve_exact_or_create(search_by, create, entity="debtor 'Acme GmbH'", step="resolve_debtor")

    assert exc_info.value.step == "resolve_debtor"
    assert "2 exact matches" in exc_info.value.reason
    assert "debtor 'Acme GmbH'" in exc_info.value.reason


def test_default_entity_and_step_appear_in_reason_when_not_given() -> None:
    with pytest.raises(ManualReviewRequired) as exc_info:
        resolve_exact_or_create(lambda: [1, 2, 3], lambda: None)

    assert exc_info.value.step == "entity_resolution"
    assert "3 exact matches for entity" in exc_info.value.reason


def test_search_by_is_called_exactly_once() -> None:
    calls = {"n": 0}

    def search_by():
        calls["n"] += 1
        return ["only-match"]

    resolve_exact_or_create(search_by, lambda: None)

    assert calls["n"] == 1


# -- search_grid_exact ----------------------------------------------------


class _FakeEdit:
    def __init__(self) -> None:
        self.set_text_calls: list[str] = []

    def set_text(self, text: str) -> None:
        self.set_text_calls.append(text)


class _FakeImage:
    def save(self, buffer, format=None) -> None:  # noqa: A002 - matches PIL's Image.save signature
        buffer.write(b"fake-png-bytes")


class _FakeGridPane:
    def capture_as_image(self):
        return _FakeImage()


class _FakeParent:
    """children() returns the Edit for control_type="Edit" and the grid
    pane for control_type="Pane", regardless of auto_id - good enough to
    exercise search_grid_exact's control-then-screenshot-then-read
    sequence without a real window.
    """

    def __init__(self, edit: _FakeEdit, grid_pane: _FakeGridPane) -> None:
        self._edit = edit
        self._grid_pane = grid_pane

    def children(self, control_type=None, title=None, auto_id=None):
        if control_type == "Edit":
            return [self._edit]
        if control_type == "Pane":
            return [self._grid_pane]
        return []


class _FakeMessages:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", name="record_grid_rows", input={"rows": self._rows})],
        )


class _FakeVisionClient:
    def __init__(self, rows: list[dict]) -> None:
        self.messages = _FakeMessages(rows)


def test_search_grid_exact_types_the_key_and_returns_vision_rows() -> None:
    edit = _FakeEdit()
    parent = _FakeParent(edit, _FakeGridPane())
    client = _FakeVisionClient(rows=[{"SKU": "ABC-1"}])

    rows = search_grid_exact(
        parent,
        search_edit_auto_id="68006",
        grid_pane_auto_id="199058",
        key="ABC-1",
        columns=["SKU"],
        vision_client=client,
        settle_seconds=0,
    )

    assert edit.set_text_calls == ["ABC-1"]
    assert rows == [{"SKU": "ABC-1"}]


def test_search_grid_exact_returns_empty_list_for_an_empty_grid() -> None:
    parent = _FakeParent(_FakeEdit(), _FakeGridPane())
    client = _FakeVisionClient(rows=[])

    rows = search_grid_exact(
        parent,
        search_edit_auto_id="68042",
        grid_pane_auto_id="854450",
        key="Cash",
        columns=["Name"],
        vision_client=client,
        settle_seconds=0,
    )

    assert rows == []
