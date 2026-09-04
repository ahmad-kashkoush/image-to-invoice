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
- read_grid_rows: pure with respect to its `client` parameter, which is
  injectable exactly like extraction.vision_extractor.extract_from_image's
  `client` - a real anthropic.Anthropic() by default, a fake exposing
  `.messages.create(...)` in tests. No pywinauto import, no network call in
  tests, fully unit-testable on macOS/Linux.
"""

from __future__ import annotations

import base64
import io
from typing import Any

import anthropic

from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.ui_automation import config

_ROWS_TOOL_NAME = "record_grid_rows"

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
