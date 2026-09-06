"""Writing and verifying one row of the Order editor's Items grid.

A different mechanism from the rest of that editor, not just a different
part of it: this grid is a custom-rendered canvas with no rows, cells or
child controls, so a value gets in by measuring the grid's own drawn
separator lines, computing a coordinate, clicking it, typing blind, and
reading the row back through a vision call to find out whether it worked.
The only place in the codebase that writes without a control to write to.

Never imports pywinauto.
"""

from __future__ import annotations

import time
from typing import Any

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
    """Fill the just-added line's Item No./Qty./Discount cells, read the
    row back, and retry from a freshly-located row before failing closed.

    Both halves exist because a live run wrote a line's Qty. into nowhere
    and said nothing - a write that misses the cell is typed into no
    focused editor and leaves no trace at all.

    The row comes from `position` (lines are added in order, so the caller
    knows which row it just added) and the column from the grid's measured
    separator lines. Neither is guessed: not Fakturama's highlight, and not
    a vision read of the cell boxes, which was measurably wrong - it put a
    quantity in the Item No. column and a discount in the Name column.

    A retry cannot undo a stray value typed elsewhere; it rewrites the
    target row only. verify_order_saved catches collateral damage.
    """
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
    """Read the grid back and compare the row for item.sku, returning one
    message per discrepant column.

    Requiring exactly one matching row is what makes the picker's retry
    loop safe: a reopened picker that added the same SKU twice is caught
    here.
    """
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
    """Screenshot the grid and measure its geometry, re-capturing a frame
    that doesn't measure cleanly.

    Two transient causes, both seen live: the capture is a screen-region
    grab, so an occluded window is photographed as whatever is on top of
    it; and the grid can be mid-relayout right after the picker closes,
    which measured as 8 columns of a 10-column grid. Re-reading is safe in
    a way re-writing is not - it still raises once the attempts are spent.
    """
    last_error: GridGeometryError | None = None
    for attempt in range(attempts):
        controls.focus_foreground(main_window)
        controls.move_pointer_away(main_window)
        grid_pane = locators.items_grid_pane(main_window, items_label=items_label)
        try:
            geometry = grid_geometry.read_grid_geometry(
                vision_grounding.capture_control_image(grid_pane),
                expected_columns=len(screens.ITEMS_GRID_RENDERED_COLUMNS),
            )
        except GridGeometryError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(settle_seconds)
            continue
        return grid_pane, geometry
    assert last_error is not None
    raise last_error


def _fill_text_cell(main_window: Any, point: tuple[int, int], value: str, *, column: str = "?") -> None:
    """Click a cell to select it, then type into it: Ctrl+A, Delete, the
    value, Tab to commit.

    These cells don't reliably expose an inline Edit to target - a
    double-click-then-find-the-editor approach could time out even with the
    cell visibly in edit state. Keyboard input straight to main_window works
    every time.

    A failure to type is converted to ManualReviewRequired naming the
    column rather than escaping as a raw pywinauto error: some cells open
    their own modal popup editor when clicked (hit live by a mislocated
    click), and a modal disables the main window.
    """
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
