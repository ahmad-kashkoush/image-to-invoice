"""Measuring and widening the column layout of Fakturama's list grids.

These grids are custom-rendered: they expose no Header, HeaderItem or
DataGrid to UIA (probed live 2026-09-15 - the Debtors grid's whole subtree is
six unnamed Panes, two Texts and the search Edit), so their columns can only
be measured from pixels and resized with the mouse. They *are* resizable: the
app shows a SIZEWE cursor over a header separator.

This matters because a too-narrow column renders its text clipped with a
trailing ellipsis, and `entity_resolution.matching` compares those cells by
exact equality. Live on 2026-09-15 the Debtors grid showed
`'Northstar Offic...'` for `'Northstar Office GmbH'`, so the five-field
debtor match could never succeed and every run created another Debtor - the
duplicate-Debtor bug ADR 0014 was meant to end. Column widths are persisted
per profile in `fakturamaviews.properties`, which is why the same code
matched on one profile and created duplicates on another.

`grid_geometry` is the sibling of this module and deliberately not reused: it
measures the *Items* grid, whose separators are dark lines over a coloured
body, and it raises if it cannot find every column. These list grids are
white with faint separators, and here a failure to measure is not fatal -
the caller falls back to reading what it can.
"""

from __future__ import annotations

import io
import time
from typing import Any

from PIL import Image
from pywinauto import mouse

# What a clipped cell ends with. The first is the real glyph; the second is
# how a vision read usually transcribes it.
_ELLIPSES = ("…", "...")

# A separator is a vertical line, so nearly every pixel down the sampled band
# is off-white. A mean-based test mistakes a selection highlight or the edge
# of a glyph for one, which live measured a separator at x=9 and dragged the
# wrong column.
_OFF_WHITE = 250
_LINE_COVERAGE = 0.9

# Two separators closer together than this are the same line found twice
# (anti-aliasing), not two columns.
_MIN_COLUMN_WIDTH = 30

# These grids are mostly white cells. A capture that is not tells us the
# pixels are not the grid's: an occluded window is photographed as whatever is
# drawn over it, and a view that has not finished painting is flat grey.
# Without this, every x passes the line test and the measurement comes back as
# a separator every _MIN_COLUMN_WIDTH pixels - live, that produced 51 evenly
# spaced "columns" and would have dragged an arbitrary part of the UI.
_MIN_WHITE_FRACTION = 0.5


def is_clipped(text: str) -> bool:
    return text.rstrip().endswith(_ELLIPSES)


def _luminance(image_bytes: bytes) -> tuple[Any, int, int]:
    image = Image.open(io.BytesIO(image_bytes)).convert("L")
    width, height = image.size
    return image.load(), width, height


def separator_positions(image_bytes: bytes) -> list[int]:
    """x offsets, within the capture, of the grid's column separators.

    Sampled over the grid's empty rows rather than its whole height, so cell
    text never contributes. The first entry is the grid's own left border.
    """
    pixels, width, height = _luminance(image_bytes)
    band = list(range(int(height * 0.45), int(height * 0.90)))
    if not band:
        return []
    white = sum(1 for y in band for x in range(width) if pixels[x, y] >= _OFF_WHITE)
    if white < _MIN_WHITE_FRACTION * width * len(band):
        return []
    needed = _LINE_COVERAGE * len(band)
    positions: list[int] = []
    last = -_MIN_COLUMN_WIDTH
    for x in range(1, width - 1):
        covered = sum(1 for y in band if pixels[x, y] < _OFF_WHITE)
        if covered >= needed and x - last >= _MIN_COLUMN_WIDTH:
            positions.append(x)
            last = x
    return positions


def _resize_handle_y(x: int, top: int, bottom: int, *, step: int = 3) -> int | None:
    """The screen y at `x` where the app offers a column-resize handle.

    Asks the app instead of guessing from pixels: hovering a header separator
    switches the cursor to SIZEWE, and nothing else in these grids does. A
    pixel heuristic for "where is the header strip" picked the pane border
    and the search row instead (live, it returned y=6 for a header at y=56)
    and dragged in the wrong place, which is silent - the drag simply does
    nothing.
    """
    import ctypes
    from ctypes import wintypes

    class _CursorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hCursor", ctypes.c_void_p),
            ("ptScreenPos", wintypes.POINT),
        ]

    user32 = ctypes.windll.user32
    sizewe = user32.LoadCursorW(None, 32644)  # IDC_SIZEWE
    for y in range(top, bottom, step):
        mouse.move(coords=(x, y))
        time.sleep(0.06)
        # A fresh struct per call: GetCursorInfo requires cbSize set every
        # time, and reusing one that has already been filled makes every call
        # after the first fail (returning 0 and leaving a stale handle behind,
        # which reads as "always ARROW").
        info = _CursorInfo()
        info.cbSize = ctypes.sizeof(_CursorInfo)
        if user32.GetCursorInfo(ctypes.byref(info)) and info.hCursor == sizewe:
            return y
    return None


def widen_column(
    grid_pane: Any,
    *,
    column_index: int,
    by_pixels: int,
    expected_columns: int | None = None,
    step_pixels: int = 5,
    step_seconds: float = 0.03,
) -> bool:
    """Drag `column_index`'s right-hand separator right by `by_pixels`.

    Returns False if the layout could not be measured, so the caller can carry
    on with whatever it already read rather than failing on a cosmetic step.
    The drag is stepped rather than a single jump: SWT tracks the pointer
    during a resize and ignores a press-and-teleport (measured live - a
    two-point drag moved nothing).
    """
    image_bytes = _capture(grid_pane)
    separators = separator_positions(image_bytes)
    # separators[0] is the pane border and separators[1] the grid's left
    # edge, so an n-column grid measures exactly n + 2 lines and column i
    # spans separators[i + 1] .. separators[i + 2].
    #
    # The count is checked exactly, not loosely. A measurement that merges two
    # lines (a column narrower than _MIN_COLUMN_WIDTH) or misses the last one
    # shifts every index after it, and the drag then resizes a different
    # column than the caller asked for - live, that squeezed Company to 25px
    # and handed the space to ZIP, which is worse than the clipping it was
    # sent to fix. Refusing to act on a measurement that does not add up is
    # the only safe response.
    if expected_columns is not None and len(separators) != expected_columns + 2:
        return False
    if len(separators) < column_index + 3:
        return False

    # Dragging one separator in these grids re-lays out *every* column by the
    # same amount, rather than just the one being dragged (measured live:
    # +150px on one separator took all six columns from 125px to 275px). So
    # the drag has to be budgeted against the space left to the right of the
    # last column, or the far columns scroll out of view - and a column the
    # caller needs to read but cannot see is worse than a clipped one. Live,
    # an unbudgeted widen pushed ZIP and City off the Debtors grid entirely.
    _, capture_width, _ = _luminance(image_bytes)
    column_count = max(len(separators) - 1, 1)
    slack = capture_width - separators[-1]
    by_pixels = min(by_pixels, slack // column_count)
    if by_pixels <= 0:
        return False

    bounds = grid_pane.rectangle()
    start_x = bounds.left + separators[column_index + 2]
    y = _resize_handle_y(start_x, bounds.top, min(bounds.top + 120, bounds.bottom))
    if y is None:
        return False

    mouse.press(button="left", coords=(start_x, y))
    time.sleep(0.4)
    for offset in range(step_pixels, by_pixels + 1, step_pixels):
        mouse.move(coords=(start_x + offset, y))
        time.sleep(step_seconds)
    time.sleep(0.2)
    mouse.release(button="left", coords=(start_x + by_pixels, y))
    return True


def _capture(control: Any) -> bytes:
    image = control.capture_as_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
