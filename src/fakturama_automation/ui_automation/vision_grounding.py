from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any, Callable

import anthropic

from fakturama_automation.ui_automation import config
from fakturama_automation.ui_automation.exceptions import GridReadError

_ROWS_TOOL_NAME = "record_grid_rows"
_LOCATED_ROWS_TOOL_NAME = "record_grid_rows_located"
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

_LOCATED_GRID_PROMPT_TEMPLATE = """\
This image is a screenshot of a results grid/table from the Fakturama \
desktop application. The grid has these columns, in order: {columns}.

Extract every visible data row (skip the header row and any empty grid \
background). For each row, give the exact text shown in each column, \
copied verbatim - do not reformat, translate, or infer a value that is not \
visibly present - and its bounding box in pixel coordinates within this \
image (top-left origin): x, y, width, height, tightly enclosing the row's \
full clickable extent (from the left edge of the grid to the right edge of \
its visible content). If the grid is empty (no data rows), call the tool \
with an empty rows list.

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
class GridRow:
    # `bbox` is (x, y, width, height) within the screenshot, not on screen.
    cells: dict[str, str]
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class ComboOption:
    # `bbox` is (x, y, width, height) within the screenshot, not on screen;
    # entity_resolution.combos converts it before clicking.
    text: str
    bbox: tuple[int, int, int, int]


def capture_control_image(control: Any) -> bytes:
    # Windows/VM-only - needs a real, on-screen control.
    image = control.capture_as_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _read_via_vision_tool(
    image_bytes: bytes,
    *,
    tool_name: str,
    tool_description: str,
    input_schema: dict,
    prompt: str,
    client: Any | None,
    what: str,
) -> dict[str, Any]:
    # Every way this can go wrong raises GridReadError, so a caller never has
    # to distinguish "the grid is empty" from "the read did not happen".
    if client is None:
        client = anthropic.Anthropic()

    tool = {
        "name": tool_name,
        "description": tool_description,
        "input_schema": input_schema,
        "strict": True,
    }
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=config.VISION_GROUNDING_MODEL_ID,
            max_tokens=config.VISION_GROUNDING_MAX_TOKENS,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
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
        raise GridReadError(f"{what} failed: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise GridReadError(f"{what} refused the request")

    tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if not tool_use_blocks:
        raise GridReadError(f"{what} did not return a {tool_name} tool call")

    block = tool_use_blocks[0]
    if block.name != tool_name:
        raise GridReadError(f"{what} returned an unexpected tool call '{block.name}'")
    return block.input


def _parsed(what: str, parse: Callable[[], Any]) -> Any:
    try:
        return parse()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise GridReadError(f"malformed {what} result: {exc}") from exc


def read_grid_rows(
    image_bytes: bytes,
    *,
    columns: list[str],
    client: Any | None = None,
) -> list[dict[str, str]]:
    what = "vision grid read"
    result = _read_via_vision_tool(
        image_bytes,
        tool_name=_ROWS_TOOL_NAME,
        tool_description="Record every visible data row of the screenshotted grid, exactly once.",
        input_schema=_rows_schema(columns),
        prompt=_GRID_PROMPT_TEMPLATE.format(columns=", ".join(columns), tool_name=_ROWS_TOOL_NAME),
        client=client,
        what=what,
    )
    return _parsed(
        what,
        lambda: [{column: str(row.get(column, "")) for column in columns} for row in result["rows"]],
    )


def read_grid_rows_located(
    image_bytes: bytes,
    *,
    columns: list[str],
    client: Any | None = None,
) -> list[GridRow]:
    what = "vision grid read"
    result = _read_via_vision_tool(
        image_bytes,
        tool_name=_LOCATED_ROWS_TOOL_NAME,
        tool_description="Record every visible data row of the screenshotted grid, located, exactly once.",
        input_schema=_located_rows_schema(columns),
        prompt=_LOCATED_GRID_PROMPT_TEMPLATE.format(
            columns=", ".join(columns), tool_name=_LOCATED_ROWS_TOOL_NAME
        ),
        client=client,
        what=what,
    )
    return _parsed(
        what,
        lambda: [
            GridRow(
                cells={column: str(row.get(column, "")) for column in columns},
                bbox=(int(row["x"]), int(row["y"]), int(row["width"]), int(row["height"])),
            )
            for row in result["rows"]
        ],
    )


def read_combo_options(
    image_bytes: bytes,
    *,
    client: Any | None = None,
) -> list[ComboOption]:
    what = "vision combo read"
    result = _read_via_vision_tool(
        image_bytes,
        tool_name=_COMBO_OPTIONS_TOOL_NAME,
        tool_description="Record every visible option row of the opened dropdown/combo box, exactly once.",
        input_schema=_combo_options_schema(),
        prompt=_COMBO_PROMPT_TEMPLATE.format(tool_name=_COMBO_OPTIONS_TOOL_NAME),
        client=client,
        what=what,
    )
    return _parsed(
        what,
        lambda: [
            ComboOption(
                text=str(option["text"]),
                bbox=(int(option["x"]), int(option["y"]), int(option["width"]), int(option["height"])),
            )
            for option in result["options"]
        ],
    )


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


def _located_rows_schema(columns: list[str]) -> dict:
    row_schema = {
        "type": "object",
        "properties": {
            **{column: {"type": "string"} for column in columns},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        "required": [*columns, "x", "y", "width", "height"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"rows": {"type": "array", "items": row_schema}},
        "required": ["rows"],
        "additionalProperties": False,
    }


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
