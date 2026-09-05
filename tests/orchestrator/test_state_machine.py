"""Tests for orchestrator.state_machine.run_workflow.

No network, no real window: the vision client is a fake exposing just
`.messages.create(...)` (same style as tests/extraction/test_vision_extractor.py
and tests/entity_resolution/test_debtor.py), and `app` is a duck-typed fake
exposing `.main_window()` over a small (control_type, title, auto_id)
registry (same style as tests/entity_resolution/test_debtor.py).

Scoped to three distinct propagation paths through the state loop rather
than a full extract-to-DONE run (which would need a working fake for every
entity/verification vision call and control lookup in the whole workflow):
a normalization failure, a UI control-discovery failure converted to
ManualReviewRequired at the loop boundary, and a downstream section's own
ManualReviewRequired (entity_resolution's ambiguous-match rule) passing
through unchanged. Each is read back from the manual review queue file
(out_dir), the same way tests/error_handling/test_manual_review.py asserts
on route_to_manual_review's output, since run_workflow itself never lets a
ManualReviewRequired propagate to the caller.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fakturama_automation.entity_resolution import config as entity_config
from fakturama_automation.orchestrator import config as orch_config
from fakturama_automation.orchestrator.state_machine import WorkflowState, run_workflow
from fakturama_automation.verification import config as verification_config


def _tool_use_response(input_data: dict, *, name: str = "record_order") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", name=name, input=input_data)],
    )


class _QueuedFakeMessages:
    """Pops one canned response per `.create()` call, in order - the calls a
    given test drives happen in a fixed, known sequence, so there is no
    need to dispatch by tool name/columns the way a fully general fake
    would.
    """

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)

    def create(self, **kwargs):
        return self._responses.pop(0)


class _FakeVisionClient:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.messages = _QueuedFakeMessages(responses)


class _FakeControl:
    def __init__(self) -> None:
        self.click_input_calls = 0

    def click_input(self, coords=None, absolute=None) -> None:
        self.click_input_calls += 1

    def set_text(self, text: str) -> None:
        pass

    def window_text(self) -> str:
        return ""

    def capture_as_image(self):
        return _FakeImage()


class _FakeImage:
    def save(self, buffer, format=None) -> None:  # noqa: A002 - matches PIL's Image.save signature
        buffer.write(b"fake-png-bytes")


class _FakeMainWindow:
    """children() looks a control up by the exact (control_type, title,
    auto_id) triple find_control passes through, mirroring
    tests/entity_resolution/test_debtor.py's _FakeMainWindow. A registry
    value may be a single control (returned as a one-element list) or an
    explicit list (to simulate an ambiguous match - more than one
    candidate for the same lookup).
    """

    def __init__(self, registry: dict[tuple, object]) -> None:
        self._registry = registry

    def children(self, control_type=None, title=None, auto_id=None):
        result = self._registry.get((control_type, title, auto_id))
        if result is None:
            return []
        return result if isinstance(result, list) else [result]


class _FakeApp:
    def __init__(self, main_window: _FakeMainWindow) -> None:
        self._main_window = main_window

    def main_window(self):
        return self._main_window


def _read_queue_entries(out_dir: Path) -> list[dict]:
    queue_path = out_dir / "manual_review_queue.jsonl"
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


_ADDRESS_CONFIDENCE = {"street": 0.9, "postal_code": 0.9, "city": 0.9, "country": 0.9}
_LINE_CONFIDENCE = {
    "sku": 0.9,
    "description": 0.9,
    "quantity": 0.9,
    "unit_net_price": 0.9,
    "vat_percent": 0.9,
    "discount": 0.9,
    "source_line_total": 0.9,
}
_ORDER_CONFIDENCE = {
    "order_date": 0.9,
    "external_reference": 0.9,
    "debtor_company_name": 0.9,
    "contact_name": 0.9,
    "alias": 0.9,
    "payment_details": 0.9,
    "payment_method": 0.9,
    "payment_status": 0.9,
    "payment_date": 0.9,
}


def _valid_record_order_input() -> dict:
    """A record_order tool call that normalizes cleanly: the golden sample
    order's numbers (WEB-2026-0714-A17, Northstar Office GmbH - net
    570.00 / VAT 108.30 / total 678.30).
    """
    return {
        "order_date": "2026-07-14",
        "external_reference": "WEB-2026-0714-A17",
        "debtor_company_name": "Northstar Office GmbH",
        "contact_name": "Jane Doe",
        "alias": "Northstar",
        "billing_address": {
            "raw_text": "Main St 1, 10553 Berlin, Germany",
            "street": "Main St 1",
            "postal_code": "10553",
            "city": "Berlin",
            "country": "Germany",
            "confidence": _ADDRESS_CONFIDENCE,
        },
        "delivery_address": {
            "raw_text": "",
            "street": None,
            "postal_code": None,
            "city": None,
            "country": None,
            "confidence": {},
        },
        "payment_details": None,
        "payment_method": "Bank Transfer",
        "payment_status": "UNPAID",
        "payment_date": None,
        "line_items": [
            {
                "sku": "CHR-ERG-01",
                "description": "Ergonomic Desk Chair",
                "quantity": "2",
                "unit_net_price": "250.00",
                "vat_percent": "19",
                "discount": "10",
                "source_line_total": "450.00",
                "confidence": _LINE_CONFIDENCE,
            },
            {
                "sku": "MAT-DESK-02",
                "description": "Anti-Fatigue Desk Mat",
                "quantity": "3",
                "unit_net_price": "40.00",
                "vat_percent": "19",
                "discount": "0",
                "source_line_total": "120.00",
                "confidence": _LINE_CONFIDENCE,
            },
        ],
        "confidence": _ORDER_CONFIDENCE,
    }


def test_normalization_failure_routes_to_manual_review(tmp_path: Path) -> None:
    """An order the vision pass could read nothing from (no debtor name, no
    line items) fails normalize_order's required-fields check before any
    UI action is attempted - app is never touched.
    """
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")
    client = _FakeVisionClient([_tool_use_response({})])
    out_dir = tmp_path / "out"

    state = run_workflow(image_path, client=client, out_dir=out_dir)

    assert state == WorkflowState.NORMALIZE
    entries = _read_queue_entries(out_dir)
    assert len(entries) == 1
    assert entries[0]["step"] == "normalization"
    assert entries[0]["source_image_path"] == str(image_path)


def test_ambiguous_new_order_button_routes_to_manual_review(tmp_path: Path) -> None:
    """A control-discovery failure (here: more than one "Create: New Order"
    button match) is converted to ManualReviewRequired at the loop
    boundary rather than crashing the run, per Doc/Design.md's "stops for
    manual review if candidates remain ambiguous".
    """
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")
    registry = {("Button", orch_config.NEW_ORDER_BUTTON_TITLE, None): [_FakeControl(), _FakeControl()]}
    app = _FakeApp(_FakeMainWindow(registry))
    client = _FakeVisionClient([_tool_use_response(_valid_record_order_input())])
    out_dir = tmp_path / "out"

    state = run_workflow(image_path, app=app, client=client, out_dir=out_dir)

    assert state == WorkflowState.OPEN_ORDER
    entries = _read_queue_entries(out_dir)
    assert len(entries) == 1
    assert entries[0]["step"] == "open_order"
    assert "2 Button controls" in entries[0]["reason"]


def test_ambiguous_debtor_match_routes_to_manual_review(tmp_path: Path) -> None:
    """entity_resolution.debtor.resolve_debtor's own ManualReviewRequired
    (more than one exact company-name match) propagates through the loop
    unchanged - step="resolve_debtor", not rewritten to a state name.
    """
    image_path = tmp_path / "order.png"
    image_path.write_bytes(b"fake-png-bytes")
    registry = {
        ("Button", orch_config.NEW_ORDER_BUTTON_TITLE, None): _FakeControl(),
        ("Pane", verification_config.ORDER_TAB_TITLE_UNSAVED, None): _FakeControl(),
        ("Text", "Debtors", None): _FakeControl(),
        ("Edit", None, entity_config.DEBTOR_SEARCH_EDIT_AUTO_ID): _FakeControl(),
        ("Pane", None, entity_config.DEBTOR_LIST_PANE_AUTO_ID): _FakeControl(),
    }
    app = _FakeApp(_FakeMainWindow(registry))
    client = _FakeVisionClient(
        [
            _tool_use_response(_valid_record_order_input(), name="record_order"),
            _tool_use_response(
                {
                    "rows": [
                        {"Company Name": "Northstar Office GmbH"},
                        {"Company Name": "Northstar Office GmbH"},
                    ]
                },
                name="record_grid_rows",
            ),
        ]
    )
    out_dir = tmp_path / "out"

    state = run_workflow(image_path, app=app, client=client, out_dir=out_dir, settle_seconds=0)

    assert state == WorkflowState.POPULATE_ORDER_FIELDS
    entries = _read_queue_entries(out_dir)
    assert len(entries) == 1
    assert entries[0]["step"] == "resolve_debtor"
    assert "Northstar Office GmbH" in entries[0]["reason"]
