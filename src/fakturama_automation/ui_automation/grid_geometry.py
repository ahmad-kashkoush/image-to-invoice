"""Deterministic cell geometry for Fakturama's custom-rendered grids.

Reads a grid screenshot's own drawn separator lines to work out where each
column and row actually is, with no vision model involved.

Why this exists, when ui_automation.vision_grounding already screenshots
these grids: reading a grid's *contents* is a genuine perception problem
(that stays with the vision model), but reading its *geometry* is not - the
grid draws full-height separators between columns and evenly-pitched lines
between rows, and those are exact. Asking a model for cell positions
instead was measurably wrong, twice: a live run wrote a line's quantity
into the Item No. column and its discount into the Name column, and a
prototype against the same screenshot placed the "Qty." cell squarely
inside Item No. Nothing raised - a click at a wrong-but-plausible
coordinate types into the wrong cell exactly as convincingly as into the
right one, which is why this is worth doing exactly rather than
approximately.

Pure: takes PNG bytes, returns numbers. No pywinauto, no network - the
caller converts to screen coordinates with the captured control's own
on-screen rectangle, the same way it already does for vision_grounding's
boxes.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from fakturama_automation.ui_automation.exceptions import GridGeometryError

# A pixel at or below this (0-255 greyscale) is "not blank background" -
# grid lines and text both sit well under it, blank cells well over.
_LINE_THRESHOLD = 235

# A column separator runs the full height of the grid; cell text never
# comes close to spanning it.
_FULL_HEIGHT_FRACTION = 0.9

# Two separators nearer than this are the same line, antialiased.
_MIN_SEPARATOR_GAP = 3

# How far a row's median brightness must move from the header strip's for
# that row to count as the start of the data area.
_HEADER_BREAK = 6

# The first column separator should sit on the grid's own left edge; further
# in means the view is scrolled and column N is not the Nth column.
_LEFT_EDGE_TOLERANCE = 4


@dataclass(frozen=True)
class GridGeometry:
    """Where a grid's columns and rows are, in screenshot pixel coordinates.

    `columns` holds one (left, right) pair per detected column, left to
    right, so a caller indexes it with the column's own position in the
    grid's known column order.
    """

    columns: list[tuple[int, int]]
    data_top: int
    row_height: int

    def cell_center(self, column_index: int, row_index: int) -> tuple[int, int]:
        """Center of the cell at (column_index, row_index), both 0-based."""
        left, right = self.columns[column_index]
        return (
            (left + right) // 2,
            self.data_top + row_index * self.row_height + self.row_height // 2,
        )


def read_grid_geometry(
    image_bytes: bytes,
    *,
    expected_columns: int,
) -> GridGeometry:
    """Measure a grid screenshot's column and row geometry.

    `expected_columns` is how many columns the caller knows this grid has.
    A different number found means the screenshot isn't what the caller
    thinks it is - horizontally scrolled, clipped, or not this grid - so it
    raises rather than returning geometry that would be confidently wrong.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("L")
    width, height = image.size
    pixels = image.load()

    columns = _column_bounds(pixels, width, height)
    if len(columns) < expected_columns:
        raise GridGeometryError(
            f"grid screenshot shows {len(columns)} column(s), expected at least {expected_columns} - "
            "the grid may be horizontally scrolled or clipped",
        )
    if columns[0][0] > _LEFT_EDGE_TOLERANCE:
        raise GridGeometryError(
            f"grid screenshot's first column starts at x={columns[0][0]}, not its left edge - "
            "the grid appears to be horizontally scrolled",
        )
    # Anything past the known columns is the blank filler the grid draws to
    # the right of its last column, not a column.
    columns = columns[:expected_columns]

    header_bottom = _header_bottom(pixels, width, height)
    lines, row_height = _row_lines(pixels, columns, header_bottom, height)
    data_top = _snap_to_row_lattice(header_bottom, lines[0], row_height)
    return GridGeometry(columns=columns, data_top=data_top, row_height=row_height)


def _separator_positions(candidates: list[int]) -> list[int]:
    """Collapse runs of adjacent dark pixels into one position per line."""
    positions: list[int] = []
    for value in candidates:
        if not positions or value > positions[-1] + _MIN_SEPARATOR_GAP:
            positions.append(value)
    return positions


def _column_bounds(pixels, width: int, height: int) -> list[tuple[int, int]]:
    """Every column's (left, right), from the full-height vertical separators."""
    full_height = height * _FULL_HEIGHT_FRACTION
    dark_columns = [
        x
        for x in range(width)
        if sum(1 for y in range(height) if pixels[x, y] < _LINE_THRESHOLD) > full_height
    ]
    separators = _separator_positions(dark_columns)
    return [(left, right) for left, right in zip(separators, separators[1:])]


def _row_median(pixels, width: int, y: int) -> int:
    """Median brightness across a row - the median ignores cell text, which
    is a minority of any row's pixels, where a mean does not.
    """
    samples = sorted(pixels[x, y] for x in range(0, width, 4))
    return samples[len(samples) // 2]


def _header_bottom(pixels, width: int, height: int) -> int:
    """Roughly where the grey header strip ends, to within a pixel or two.

    Only an estimate: the exact top of the first data row comes from
    _snap_to_row_lattice, since the row separators locate the rows far more
    precisely than this brightness break locates the header's last pixel.
    """
    header_grey = _row_median(pixels, width, 4)
    for y in range(4, height):
        if abs(_row_median(pixels, width, y) - header_grey) > _HEADER_BREAK:
            return y
    raise GridGeometryError(
        "grid screenshot has no data area below its header strip"
    )


def _row_lines(
    pixels, columns: list[tuple[int, int]], header_bottom: int, height: int
) -> tuple[list[int], int]:
    """The horizontal row separators below the header, and their pitch.

    Scanned down the 4th column ("Picture" in the order/invoice item grid),
    which renders blank, so cell content can never be mistaken for a row
    line. Only lines with blank pixels above and below count, which skips
    the solid band of a highlighted row.
    """
    left, right = columns[3] if len(columns) > 3 else columns[-1]
    scan_x = (left + right) // 2
    lines = [
        y
        for y in range(header_bottom + 2, height - 2)
        if pixels[scan_x, y] < _LINE_THRESHOLD
        and pixels[scan_x, y - 2] >= _LINE_THRESHOLD
        and pixels[scan_x, y + 2] >= _LINE_THRESHOLD
    ]
    pitches = sorted(b - a for a, b in zip(lines, lines[1:]))
    if not pitches:
        raise GridGeometryError(
            "grid screenshot shows no row separators - cannot measure row height"
        )
    if pitches[0] != pitches[-1]:
        raise GridGeometryError(
            f"grid rows are not evenly pitched (measured {pitches!r})"
        )
    return lines, pitches[0]


def _snap_to_row_lattice(header_bottom: int, first_line: int, row_height: int) -> int:
    """The first data row's top: the row-lattice position nearest the
    header's lower edge.

    Row separators sit on an exact `row_height` lattice, so stepping back up
    from the first one gives every row boundary precisely; the header
    brightness break only says roughly where to stop. Snapping the estimate
    onto the lattice takes the accurate number from each. Demanding the two
    agree exactly instead is too brittle - live, they came out one pixel
    apart and a whole run failed closed over it.
    """
    candidates = [y for y in range(first_line, -1, -row_height) if y >= header_bottom - row_height // 2]
    if not candidates:
        raise GridGeometryError(
            f"no row boundary lines up with the header's lower edge ({header_bottom}) "
            f"stepping back from {first_line} at a {row_height}px pitch",
        )
    return min(candidates)
