"""Tests for entity_resolution.resolver.resolve_exact_or_create.

Pure function tests - search_by/create are plain callables, no UI, no
network. search_grid_exact (pywinauto/vision-grounded) is not unit tested;
verify it live on the VM instead.
"""

from __future__ import annotations

import pytest

from fakturama_automation.entity_resolution.resolver import resolve_exact_or_create
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
