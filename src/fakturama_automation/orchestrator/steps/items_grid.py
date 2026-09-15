
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fakturama_automation.error_handling import config as error_handling_config
from fakturama_automation.error_handling.exceptions import ManualReviewRequired
from fakturama_automation.normalization.models import NormalizedLineItem
from fakturama_automation.orchestrator import config
from fakturama_automation.ui_automation import (
    controls,
    grid_geometry,
    locators,
    screens,
    vision_grounding,
)
from fakturama_automation.ui_automation.exceptions import GridGeometryError
from fakturama_automation.verification import comparisons

# Matches state_machine.WorkflowState.ADD_ORDER_LINES.value, so a problem
# raised here lands in the queue under the same step as one raised by the
# loop. Not imported from state_machine, which imports this package.
ADD_LINES_STEP = "add_order_lines"


def fill_and_verify_line(
    main_window: Any,
    items_label: Any,
    item: NormalizedLineItem,
    *,
    position: int,
    client: Any,
    settle_seconds: float,
    attempts: int = config.ORDER_LINE_FILL_ATTEMPTS,
) -> None:
    # Plain str(), i.e. a "." decimal separator, deliberately - and NOT
    # normalization.parsing.format_decimal, which the Product form needs.
    # Fakturama is not internally consistent about number locale, and the
    # line runs between form Edits and grid cells: measured live 2026-09-15,
    # the Product price and the Invoice payment Value both parse "." as a
    # thousands separator ("297.50" -> 29750), while this grid does the
    # opposite - "2,00" here becomes 200, and it renders "45,000.00". So grid
    # cells keep str() and only form Edits use ui_config.DECIMAL_SEPARATOR.
    #
    # U.Price is deliberately absent from this dict: it is not typed at all -
    # the picker fills it from the Product record, which is why a product
    # created with a mis-parsed price surfaces here as a wrong U.Price rather
    # than as a typing bug in this function.
    values = {
        screens.ITEMS_COL_SKU: item.sku,
        screens.ITEMS_COL_QUANTITY: str(item.quantity),
        screens.ITEMS_COL_DISCOUNT: str(item.discount),
    }
    problems: list[str] = []
    for _attempt in range(attempts):
        grid_pane, geometry = _measure_grid(main_window, items_label, settle_seconds=settle_seconds)
        row_bounds = grid_pane.rectangle()

        for column in screens.ITEMS_GRID_FILL_COLUMNS:
            cx, cy = geometry.cell_center(
                screens.ITEMS_GRID_RENDERED_COLUMNS.index(column), position - 1
            )
            point = (row_bounds.left + cx, row_bounds.top + cy)
            _fill_text_cell(main_window, point, values[column], column=column)
        time.sleep(settle_seconds)

        problems = row_problems(main_window, items_label, item, client=client)
        if not problems:
            return

    raise ManualReviewRequired(
        ADD_LINES_STEP,
        f"line {position} ('{item.sku}') still wrong after {attempts} fill attempt(s): " + "; ".join(problems),
    )


def row_problems(
    main_window: Any, items_label: Any, item: NormalizedLineItem, *, client: Any
) -> list[str]:
    controls.focus_foreground(main_window)
    # The pointer still rests on the last cell written, and its tooltip
    # would be drawn over the row about to be read.
    controls.move_pointer_away(main_window)
    grid_pane = locators.items_grid_pane(main_window, items_label=items_label)
    rows = vision_grounding.read_grid_rows(
        vision_grounding.capture_control_image(grid_pane),
        columns=screens.ITEMS_GRID_READ_COLUMNS,
        client=client,
    )
    matches = [
        row for row in rows if comparisons.text_equals(item.sku, row.get(screens.ITEMS_COL_SKU, ""))
    ]
    if len(matches) != 1:
        return [
            f"{len(matches)} row(s) in the Items grid have Item No. '{item.sku}' after adding it "
            f"(expected exactly one, out of {len(rows)} row(s) read)"
        ]
    return comparisons.line_row_problems(item, matches[0])


def _measure_grid(
    main_window: Any,
    items_label: Any,
    *,
    settle_seconds: float,
    attempts: int = config.GRID_MEASURE_ATTEMPTS,
) -> tuple[Any, grid_geometry.GridGeometry]:
    # Two transient causes, both seen live: the capture is a screen-region
    # grab, so an occluded window is photographed as whatever is on top of it;
    # and the grid can be mid-relayout right after the picker closes, which
    # measured as 8 columns of a 10-column grid. Re-reading is safe in a way
    # re-writing is not - it still raises once the attempts are spent.
    last_error: GridGeometryError | None = None
    last_image: bytes | None = None
    for attempt in range(attempts):
        controls.focus_foreground(main_window)
        controls.move_pointer_away(main_window)
        grid_pane = locators.items_grid_pane(main_window, items_label=items_label)
        image = vision_grounding.capture_control_image(grid_pane)
        try:
            geometry = grid_geometry.read_grid_geometry(
                image,
                expected_columns=len(screens.ITEMS_GRID_RENDERED_COLUMNS),
            )
        except GridGeometryError as exc:
            last_error = exc
            last_image = image
            if attempt + 1 < attempts:
                time.sleep(settle_seconds)
            continue
        return grid_pane, geometry
    assert last_error is not None
    # The measurement is made of pixels, so the message alone cannot be
    # debugged - both geometry faults found live so far (ADR 0021, and the
    # selection highlight below) needed the picture, and by the time anyone
    # reads the queue entry the screen is long gone. Keeping the capture that
    # failed costs one PNG per stopped run.
    raise GridGeometryError(f"{last_error} - capture saved to {_dump_capture(last_image)}")


def _dump_capture(image_bytes: bytes | None) -> str:
    if image_bytes is None:
        return "(nothing captured)"
    path = Path(error_handling_config.OUT_DIR) / f"grid-measure-{time.strftime('%Y%m%d-%H%M%S')}.png"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
    except OSError as exc:  # a failed dump must not replace the real error
        return f"(could not be saved: {exc})"
    return str(path)


def _fill_text_cell(main_window: Any, point: tuple[int, int], value: str, *, column: str = "?") -> None:
    # These cells do not reliably expose an inline Edit to target - a
    # double-click-then-find-the-editor approach timed out even with the cell
    # visibly in edit state. Keyboard input straight to main_window works.
    #
    # A failure to type is converted to ManualReviewRequired naming the column
    # rather than escaping as a raw pywinauto error: some cells open their own
    # modal popup editor when clicked, and a modal disables the main window.
    controls.focus(main_window)
    main_window.click_input(coords=point, absolute=True)
    try:
        main_window.type_keys("^a{DELETE}")
        main_window.type_keys(controls.escape_send_keys(value), with_spaces=True)
        main_window.type_keys("{TAB}")
    except Exception as exc:  # noqa: BLE001 - pywinauto ElementNotEnabled and friends
        raise ManualReviewRequired(
            ADD_LINES_STEP,
            f"could not type {value!r} into the {column} cell at {point}: {type(exc).__name__} - "
            "the main window was not accepting input (a modal popup editor may have opened)",
        ) from exc
