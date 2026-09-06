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
    # Screenshot pixel coordinates. `columns` holds one (left, right) pair per
    # detected column, left to right, so a caller indexes it with the column's
    # own position in the grid's known column order.
    columns: list[tuple[int, int]]
    data_top: int
    row_height: int

    def cell_center(self, column_index: int, row_index: int) -> tuple[int, int]:
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
    # Finding a different number of columns than `expected_columns` means the
    # screenshot is not what the caller thinks it is - scrolled, clipped, or
    # not this grid - so it raises rather than returning geometry that would be
    # confidently wrong.
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
    columns = columns[:expected_columns]

    header_bottom = _header_bottom(pixels, width, height)
    lines, row_height = _row_lines(pixels, columns, header_bottom, height)
    data_top = _snap_to_row_lattice(header_bottom, lines[0], row_height)
    return GridGeometry(columns=columns, data_top=data_top, row_height=row_height)


def _separator_positions(candidates: list[int]) -> list[int]:
    positions: list[int] = []
    for value in candidates:
        if not positions or value > positions[-1] + _MIN_SEPARATOR_GAP:
            positions.append(value)
    return positions


def _column_bounds(pixels, width: int, height: int) -> list[tuple[int, int]]:
    full_height = height * _FULL_HEIGHT_FRACTION
    dark_columns = [
        x
        for x in range(width)
        if sum(1 for y in range(height) if pixels[x, y] < _LINE_THRESHOLD) > full_height
    ]
    separators = _separator_positions(dark_columns)
    return [(left, right) for left, right in zip(separators, separators[1:])]


def _row_median(pixels, width: int, y: int) -> int:
    samples = sorted(pixels[x, y] for x in range(0, width, 4))
    return samples[len(samples) // 2]


def _header_bottom(pixels, width: int, height: int) -> int:
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
    candidates = [y for y in range(first_line, -1, -row_height) if y >= header_bottom - row_height // 2]
    if not candidates:
        raise GridGeometryError(
            f"no row boundary lines up with the header's lower edge ({header_bottom}) "
            f"stepping back from {first_line} at a {row_height}px pitch",
        )
    return min(candidates)
