"""Tests for ui_automation.controls.

Fake parent objects duck-type only pywinauto's own `children(control_type=,
title=)` method - no pywinauto import here, so these tests run on
macOS/Linux without a real window or the uia backend.
"""

from __future__ import annotations

import time

import pytest

from fakturama_automation.ui_automation.controls import find_all_controls, find_control
from fakturama_automation.ui_automation.exceptions import AmbiguousControlError, ControlNotFoundError


class FakeElement:
    def __init__(self, name: str) -> None:
        self._name = name

    def window_text(self) -> str:
        return self._name


class FakeParent:
    """children() returns the next entry from a fixed list of "poll
    responses" (repeating the last one once exhausted), so tests can
    simulate a control appearing after a few polls.
    """

    def __init__(self, responses: list[list[FakeElement]]) -> None:
        self._responses = responses
        self.calls = 0

    def children(self, control_type=None, title=None):
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[index]


def test_find_all_controls_passes_control_type_and_title_through() -> None:
    seen: dict = {}

    class RecordingParent:
        def children(self, **kwargs):
            seen.update(kwargs)
            return []

    find_all_controls(RecordingParent(), "Button", "Save")
    assert seen == {"control_type": "Button", "title": "Save"}


def test_find_all_controls_omits_title_when_name_is_none() -> None:
    seen: dict = {}

    class RecordingParent:
        def children(self, **kwargs):
            seen.update(kwargs)
            return []

    find_all_controls(RecordingParent(), "Button")
    assert seen == {"control_type": "Button"}


def test_find_control_returns_single_immediate_match() -> None:
    parent = FakeParent([[FakeElement("Save")]])
    result = find_control(parent, "Button", "Save", timeout_seconds=0.2)
    assert result.window_text() == "Save"
    assert parent.calls == 1


def test_find_control_retries_until_control_appears() -> None:
    parent = FakeParent([[], [], [FakeElement("Save")]])
    result = find_control(parent, "Button", "Save", timeout_seconds=1.0)
    assert result.window_text() == "Save"
    assert parent.calls == 3


def test_find_control_raises_not_found_after_timeout() -> None:
    parent = FakeParent([[]])
    with pytest.raises(ControlNotFoundError):
        find_control(parent, "Button", "Save", timeout_seconds=0.3)


def test_find_control_raises_ambiguous_immediately_without_waiting_out_timeout() -> None:
    parent = FakeParent([[FakeElement("Save"), FakeElement("Save")]])
    start = time.monotonic()
    with pytest.raises(AmbiguousControlError):
        find_control(parent, "Button", "Save", timeout_seconds=5.0)
    assert time.monotonic() - start < 1.0  # did not wait out the 5s timeout
