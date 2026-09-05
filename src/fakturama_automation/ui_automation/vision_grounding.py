"""Vision-based reading of custom-rendered (non-UIA) grid controls.

Section 3 (ui_automation), added for Section 4 (entity_resolution) and
reused by Section 5 (verification). Doc/Design.md's control discovery
section explicitly sanctions this: "OCR or visual inspection can
disambiguate a control when UIA metadata is insufficient (for example, a
custom-rendered element); the actual interaction still targets the
corresponding UIA element rather than falling back to coordinate-based
clicking." Fakturama's list/search result grids (Debtors, Products,
Products, VATs, terms of payment) are exactly this case: probing them
(probes/probe-06-debitors.txt, probe-07-products.txt,
probe-09-Payment.txt) found each results pane has no child controls at
all - no DataItem/ListItem rows, no readable cell text - so entity
resolution's "search, then read the result rows" step cannot be done with
controls.find_all_controls the way every other Section 3 lookup is.

This module is split in two, matching the same seam ui_automation already
uses elsewhere (Doc/adr/0002):

- capture_control_image: the one function that touches a live pywinauto
  control (`.capture_as_image()`). Windows/VM-only, like ui_automation.app;
  not unit tested here for the same reason app.py isn't.
- read_grid_rows / read_combo_options: pure with respect to their `client`
  parameter, which is injectable exactly like
  extraction.vision_extractor.extract_from_image's `client` - a real
  anthropic.Anthropic() by default, a fake exposing `.messages.create(...)`
  in tests. No pywinauto import, no network call in tests, fully
  unit-testable on macOS/Linux.

read_combo_options is the Section 4 residual's addition (Doc/adr/0006):
Fakturama's ComboBox dropdown popups turned out to be just as UIA-opaque
as the list grids (probes/probe-11-product-vat-combo-open.txt,
probes/probe-12-debito-country-combo-open.txt: a single childless Pane),
and - unlike the list grids - that popup isn't even a descendant of the
main window, so there's no UIA element left to `.select()` an option on.
entity_resolution.combos works around this by screenshotting the main
window itself right after opening the combo (capture_control_image is a
screen-rect grab, not a UIA-tree walk, so it captures the dropdown overlay
too) and asking read_combo_options to both name and locate
(`ComboOption.bbox`) each option, so the caller can click the matched
option's screen coordinate directly instead of selecting it via UIA.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any

import anthropic

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation import config

_ROWS_TOOL_NAME = "record_grid_rows"
_COMBO_OPTIONS_TOOL_NAME = "record_combo_options"

_GRID_PROMPT_TEMPLATE = """\
This image is a screenshot of a results grid/table from the Fakturama \
desktop application. The grid has these columns, in order: {columns}.

Extract every visible data row (skip the header row and any empty grid \
background). For each row, give the exact text shown in each column, \
copied verbatim - do not reformat, translate, or infer a value that is not \
visibly present. If the grid is empty (no data rows), call the tool with \
an empty rows list.

Call the {tool_name} tool exactly once with the complete result.
"""

_COMBO_PROMPT_TEMPLATE = """\
This image is a screenshot of the Fakturama desktop application, taken \
immediately after opening a dropdown/combo box. The dropdown's list of \
selectable options is visible as an overlay somewhere in this image (a \
rectangular list of text rows, usually appearing just below or over the \
combo box that was clicked).

Identify every visible option row in that dropdown list only - ignore \
every other control in the screenshot (toolbars, other fields, the rest \
of the window). For each option, give its exact text, copied verbatim, \
and its bounding box in pixel coordinates within this image (top-left \
origin): x, y, width, height, tightly enclosing the option's clickable \
row. If no dropdown list is visible, call the tool with an empty options \
list.

Call the {tool_name} tool exactly once with the complete result.
"""


@dataclass(frozen=True)
class ComboOption:
    """One option row read back from an opened combo/dropdown.

    `bbox` is (x, y, width, height) in pixel coordinates within the
    screenshot passed to read_combo_options - not screen coordinates.
    entity_resolution.combos converts it to an absolute screen point
    before clicking (see its docstring for why: the popup itself isn't
    reachable as a UIA control to click_input() on directly).
    """

    text: str
    bbox: tuple[int, int, int, int]


def capture_control_image(control: Any) -> bytes:
    """Screenshot a live pywinauto control (typically a results grid pane)
    and return it as PNG bytes.

    `control` is whatever pywinauto object (a UIAWrapper) the caller
    already holds - only its documented `.capture_as_image()` method is
    used, mirroring controls.py/waits.py's duck-typed seam (Doc/adr/0002).
    This function is exercised only against a real Fakturama window on the
    Windows 11 ARM VM; it has no unit test for the same reason
    ui_automation.app has none - `.capture_as_image()` needs a real,
    on-screen control to capture.
    """
    image = control.capture_as_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def read_grid_rows(
    image_bytes: bytes,
    *,
    columns: list[str],
    client: Any | None = None,
    step: str = "ui_automation.read_grid_rows",
) -> list[dict[str, str]]:
    """Read the visible rows of a custom-rendered grid from a screenshot.

    Returns a list of {column_name: cell_text} dicts, one per visible data
    row, in on-screen order. `client` is injectable (an anthropic-compatible
    client, or a test double exposing `.messages.create(...)`) so this can
    be tested without a real API key or network access; it defaults to a
    real `anthropic.Anthropic()` client.

    A failed vision call, a refusal, or a malformed response all raise
    ManualReviewRequired rather than returning an empty/partial row list:
    this feeds directly into entity_resolution's exact-match counting, and
    an empty result must mean "the grid is actually empty", never "the read
    failed" (Doc/Design.md's fail-closed principle - CLAUDE.md's "A missing
    confidence score ... is treated as 0.0" applies here in spirit: an
    uncertain read is never treated as a confident zero-match).
    """
    if client is None:
        client = anthropic.Anthropic()

    tool = {
        "name": _ROWS_TOOL_NAME,
        "description": "Record every visible data row of the screenshotted grid, exactly once.",
        "input_schema": _rows_schema(columns),
        "strict": True,
    }
    prompt = _GRID_PROMPT_TEMPLATE.format(columns=", ".join(columns), tool_name=_ROWS_TOOL_NAME)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=config.VISION_GROUNDING_MODEL_ID,
            max_tokens=config.VISION_GROUNDING_MAX_TOKENS,
            tools=[tool],
            tool_choice={"type": "tool", "name": _ROWS_TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except Exception as exc:  # anthropic.APIError and friends, or a fake client's own errors
        raise ManualReviewRequired(step=step, reason=f"vision grid read failed: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise ManualReviewRequired(step=step, reason="vision grid read refused the request")

    tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if not tool_use_blocks:
        raise ManualReviewRequired(step=step, reason=f"vision grid read did not return a {_ROWS_TOOL_NAME} tool call")

    block = tool_use_blocks[0]
    if block.name != _ROWS_TOOL_NAME:
        raise ManualReviewRequired(step=step, reason=f"unexpected tool call '{block.name}'")

    try:
        rows = block.input["rows"]
        return [{column: str(row.get(column, "")) for column in columns} for row in rows]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ManualReviewRequired(step=step, reason=f"malformed grid read result: {exc}") from exc


def _rows_schema(columns: list[str]) -> dict:
    row_schema = {
        "type": "object",
        "properties": {column: {"type": "string"} for column in columns},
        "required": list(columns),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"rows": {"type": "array", "items": row_schema}},
        "required": ["rows"],
        "additionalProperties": False,
    }


def read_combo_options(
    image_bytes: bytes,
    *,
    client: Any | None = None,
    step: str = "ui_automation.read_combo_options",
) -> list[ComboOption]:
    """Read the visible option rows of an opened combo/dropdown from a
    screenshot, each with its bounding box within that screenshot.

    Mirrors read_grid_rows' injectable-client, tool-forced-call shape
    (same failure handling: a failed call, a refusal, or a malformed
    response all raise ManualReviewRequired rather than returning an
    empty/partial list - an uncertain read must never be mistaken for "the
    dropdown has no options"). The bbox is the one thing read_grid_rows
    doesn't need: there is no UIA element to .select() on an option here
    (entity_resolution.combos.pick_option's caller clicks the matched
    option's screen coordinate instead), so the model is asked to locate
    each option, not just transcribe it.
    """
    if client is None:
        client = anthropic.Anthropic()

    tool = {
        "name": _COMBO_OPTIONS_TOOL_NAME,
        "description": "Record every visible option row of the opened dropdown/combo box, exactly once.",
        "input_schema": _combo_options_schema(),
        "strict": True,
    }
    prompt = _COMBO_PROMPT_TEMPLATE.format(tool_name=_COMBO_OPTIONS_TOOL_NAME)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=config.VISION_GROUNDING_MODEL_ID,
            max_tokens=config.VISION_GROUNDING_MAX_TOKENS,
            tools=[tool],
            tool_choice={"type": "tool", "name": _COMBO_OPTIONS_TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except Exception as exc:  # anthropic.APIError and friends, or a fake client's own errors
        raise ManualReviewRequired(step=step, reason=f"vision combo read failed: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise ManualReviewRequired(step=step, reason="vision combo read refused the request")

    tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if not tool_use_blocks:
        raise ManualReviewRequired(
            step=step, reason=f"vision combo read did not return a {_COMBO_OPTIONS_TOOL_NAME} tool call"
        )

    block = tool_use_blocks[0]
    if block.name != _COMBO_OPTIONS_TOOL_NAME:
        raise ManualReviewRequired(step=step, reason=f"unexpected tool call '{block.name}'")

    try:
        options = block.input["options"]
        return [
            ComboOption(
                text=str(option["text"]),
                bbox=(int(option["x"]), int(option["y"]), int(option["width"]), int(option["height"])),
            )
            for option in options
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ManualReviewRequired(step=step, reason=f"malformed combo read result: {exc}") from exc


def _combo_options_schema() -> dict:
    option_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        "required": ["text", "x", "y", "width", "height"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"options": {"type": "array", "items": option_schema}},
        "required": ["options"],
        "additionalProperties": False,
    }
