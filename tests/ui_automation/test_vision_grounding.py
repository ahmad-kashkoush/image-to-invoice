"""Tests for ui_automation.vision_grounding.read_grid_rows.

No network calls, no real screenshot: the anthropic client is replaced
with a fake exposing just `.messages.create(...)`, matching the injectable
`client` parameter - same pattern as
tests/extraction/test_vision_extractor.py. capture_control_image is not
tested here: it needs a real, on-screen pywinauto control
(`.capture_as_image()`), so like ui_automation.app it can only be
exercised on the Windows 11 ARM VM.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation.vision_grounding import ComboOption, read_combo_options, read_grid_rows

_FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-bytes"


def _tool_use_block(input_data: dict, name: str = "record_grid_rows") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_data)


def _text_block() -> SimpleNamespace:
    return SimpleNamespace(type="text", text="hello")


class FakeMessages:
    def __init__(self, response: SimpleNamespace | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, response: SimpleNamespace | None = None, error: Exception | None = None) -> None:
        self.messages = FakeMessages(response=response, error=error)


def _response(rows: list[dict], stop_reason: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[_tool_use_block({"rows": rows})],
    )


def test_returns_rows_from_the_tool_call() -> None:
    client = FakeClient(response=_response([{"Company Name": "Northstar Office GmbH"}]))

    rows = read_grid_rows(_FAKE_PNG_BYTES, columns=["Company Name"], client=client)

    assert rows == [{"Company Name": "Northstar Office GmbH"}]


def test_returns_empty_list_for_an_empty_grid() -> None:
    client = FakeClient(response=_response([]))

    rows = read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client)

    assert rows == []


def test_fills_missing_columns_with_empty_string() -> None:
    # A row missing a column in the model's response is not treated as a
    # parse failure - it's normalized to "" so exact_text_matches never
    # sees a KeyError, consistent with the rest of this codebase treating a
    # missing value as absent rather than raising.
    client = FakeClient(response=_response([{"SKU": "ABC-1"}]))

    rows = read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU", "Description"], client=client)

    assert rows == [{"SKU": "ABC-1", "Description": ""}]


def test_passes_model_and_forced_tool_choice() -> None:
    client = FakeClient(response=_response([]))

    read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client)

    kwargs = client.messages.last_call_kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_grid_rows"}
    assert kwargs["tools"][0]["name"] == "record_grid_rows"
    assert "SKU" in kwargs["messages"][0]["content"][1]["text"]


def test_raises_manual_review_when_the_client_call_fails() -> None:
    client = FakeClient(error=RuntimeError("network down"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client, step="entity_resolution.search")

    assert exc_info.value.step == "entity_resolution.search"
    assert "network down" in exc_info.value.reason


def test_raises_manual_review_on_refusal() -> None:
    client = FakeClient(response=SimpleNamespace(stop_reason="refusal", content=[]))

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client)

    assert "refused" in exc_info.value.reason


def test_raises_manual_review_when_no_tool_call_returned() -> None:
    client = FakeClient(response=SimpleNamespace(stop_reason="end_turn", content=[_text_block()]))

    with pytest.raises(ManualReviewRequired):
        read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client)


def test_raises_manual_review_on_unexpected_tool_name() -> None:
    client = FakeClient(response=SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block({}, name="other_tool")]))

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client)

    assert "other_tool" in exc_info.value.reason


def test_raises_manual_review_on_malformed_result() -> None:
    client = FakeClient(
        response=SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block({"not_rows": []})])
    )

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_grid_rows(_FAKE_PNG_BYTES, columns=["SKU"], client=client)

    assert "malformed" in exc_info.value.reason


# -- read_combo_options ---------------------------------------------------


def _combo_response(options: list[dict], stop_reason: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[_tool_use_block({"options": options}, name="record_combo_options")],
    )


def test_returns_options_with_bbox_from_the_tool_call() -> None:
    client = FakeClient(
        response=_combo_response([{"text": "19 %", "x": 10, "y": 20, "width": 50, "height": 15}])
    )

    options = read_combo_options(_FAKE_PNG_BYTES, client=client)

    assert options == [ComboOption(text="19 %", bbox=(10, 20, 50, 15))]


def test_returns_empty_list_for_a_closed_or_empty_dropdown() -> None:
    client = FakeClient(response=_combo_response([]))

    options = read_combo_options(_FAKE_PNG_BYTES, client=client)

    assert options == []


def test_combo_passes_model_and_forced_tool_choice() -> None:
    client = FakeClient(response=_combo_response([]))

    read_combo_options(_FAKE_PNG_BYTES, client=client)

    kwargs = client.messages.last_call_kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_combo_options"}
    assert kwargs["tools"][0]["name"] == "record_combo_options"


def test_combo_raises_manual_review_when_the_client_call_fails() -> None:
    client = FakeClient(error=RuntimeError("network down"))

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_combo_options(_FAKE_PNG_BYTES, client=client, step="entity_resolution.select_vat_option")

    assert exc_info.value.step == "entity_resolution.select_vat_option"
    assert "network down" in exc_info.value.reason


def test_combo_raises_manual_review_on_refusal() -> None:
    client = FakeClient(response=SimpleNamespace(stop_reason="refusal", content=[]))

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_combo_options(_FAKE_PNG_BYTES, client=client)

    assert "refused" in exc_info.value.reason


def test_combo_raises_manual_review_when_no_tool_call_returned() -> None:
    client = FakeClient(response=SimpleNamespace(stop_reason="end_turn", content=[_text_block()]))

    with pytest.raises(ManualReviewRequired):
        read_combo_options(_FAKE_PNG_BYTES, client=client)


def test_combo_raises_manual_review_on_unexpected_tool_name() -> None:
    client = FakeClient(
        response=SimpleNamespace(
            stop_reason="tool_use", content=[_tool_use_block({}, name="other_tool")]
        )
    )

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_combo_options(_FAKE_PNG_BYTES, client=client)

    assert "other_tool" in exc_info.value.reason


def test_combo_raises_manual_review_on_malformed_result() -> None:
    client = FakeClient(
        response=SimpleNamespace(
            stop_reason="tool_use", content=[_tool_use_block({"not_options": []}, name="record_combo_options")]
        )
    )

    with pytest.raises(ManualReviewRequired) as exc_info:
        read_combo_options(_FAKE_PNG_BYTES, client=client)

    assert "malformed" in exc_info.value.reason
