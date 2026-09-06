"""Tests for ui_automation.grid_geometry.

`read_grid_geometry` is pure - PNG bytes in, numbers out - and it is the
most subtle deterministic code in the repo: five tuned pixel thresholds and
a lattice-snapping step that was added after a live run failed closed over a
one-pixel disagreement. It also sits directly on the path that writes
quantities into an accounting document, where a wrong-but-plausible
coordinate types into the wrong cell exactly as convincingly as into the
right one. So it is worth pinning.

**What these tests do and don't cover.** The fixture is *synthetic*: a grid
drawn here to the structure the algorithm expects (a grey header strip,
full-height column separators, evenly pitched row lines). That pins the
contract - column count and bounds, where the first data row starts, the
scroll and clipping rejections, and that the darkness threshold is what
distinguishes a separator from background - so a future change to
grid_geometry cannot silently move any of them.

It does *not* prove the algorithm agrees with how Fakturama actually renders
its Items grid; only a capture from the real app can do that, and this
project has no way to take one off the VM. Replacing `_grid_png` with a
committed real screenshot is the stronger version of this test and is worth
doing on the next VM session - the assertions below would mostly carry over
unchanged.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from fakturama_automation.ui_automation.exceptions import GridGeometryError
from fakturama_automation.ui_automation.grid_geometry import read_grid_geometry

# The synthetic grid's own known geometry, which the assertions below are
# stated in terms of rather than as bare magic numbers.
WIDTH = 600
HEIGHT = 200
HEADER_HEIGHT = 25
FIRST_SEPARATOR_X = 2
COLUMN_WIDTH = 55
COLUMN_COUNT = 10
ROW_HEIGHT = 20
FIRST_ROW_LINE_Y = HEADER_HEIGHT + ROW_HEIGHT  # 45

HEADER_GREY = 200
BACKGROUND = 255
LINE_DARK = 100


def _grid_png(
    *,
    columns: int = COLUMN_COUNT,
    line_colour: int = LINE_DARK,
) -> bytes:
    """Draw a grid to the structure grid_geometry reads: a grey header
    strip, `columns + 1` full-height column separators, and evenly pitched
    horizontal row lines below the header.
    """
    image = Image.new("L", (WIDTH, HEIGHT), BACKGROUND)
    pixels = image.load()

    for y in range(HEADER_HEIGHT):
        for x in range(WIDTH):
            pixels[x, y] = HEADER_GREY

    for index in range(columns + 1):
        x = FIRST_SEPARATOR_X + index * COLUMN_WIDTH
        if x >= WIDTH:
            break
        for y in range(HEIGHT):
            pixels[x, y] = line_colour

    y = FIRST_ROW_LINE_Y
    while y < HEIGHT - 2:
        for x in range(WIDTH):
            pixels[x, y] = line_colour
        y += ROW_HEIGHT

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _cropped_from(image_bytes: bytes, left: int) -> bytes:
    """The same grid scrolled horizontally: the left edge cut off, so the
    first separator no longer sits on it.
    """
    image = Image.open(io.BytesIO(image_bytes)).crop((left, 0, WIDTH, HEIGHT))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# -- the happy path ---------------------------------------------------------


def test_measures_every_column() -> None:
    geometry = read_grid_geometry(_grid_png(), expected_columns=COLUMN_COUNT)

    assert len(geometry.columns) == COLUMN_COUNT
    assert geometry.columns[0] == (FIRST_SEPARATOR_X, FIRST_SEPARATOR_X + COLUMN_WIDTH)
    assert geometry.columns[-1] == (
        FIRST_SEPARATOR_X + (COLUMN_COUNT - 1) * COLUMN_WIDTH,
        FIRST_SEPARATOR_X + COLUMN_COUNT * COLUMN_WIDTH,
    )


def test_finds_the_row_lattice() -> None:
    geometry = read_grid_geometry(_grid_png(), expected_columns=COLUMN_COUNT)

    assert geometry.row_height == ROW_HEIGHT
    # Snapped back from the first row line onto the lattice, landing on the
    # header's lower edge rather than a row further down.
    assert geometry.data_top == HEADER_HEIGHT


def test_cell_center_lands_inside_the_intended_cell() -> None:
    geometry = read_grid_geometry(_grid_png(), expected_columns=COLUMN_COUNT)

    # Row 0 of column 0: half a column in, half a row down from data_top.
    assert geometry.cell_center(0, 0) == (
        FIRST_SEPARATOR_X + COLUMN_WIDTH // 2,
        HEADER_HEIGHT + ROW_HEIGHT // 2,
    )
    # A later cell stays on the same lattice - the failure that motivated
    # this module put a second line's quantity in the wrong column.
    left, right = geometry.columns[2]
    x, y = geometry.cell_center(2, 1)
    assert left < x < right
    assert HEADER_HEIGHT + ROW_HEIGHT < y < HEADER_HEIGHT + 2 * ROW_HEIGHT


def test_extra_columns_beyond_the_expected_count_are_ignored() -> None:
    # The grid draws blank filler to the right of its last real column.
    geometry = read_grid_geometry(_grid_png(), expected_columns=COLUMN_COUNT - 2)

    assert len(geometry.columns) == COLUMN_COUNT - 2


# -- the fail-closed paths --------------------------------------------------


def test_fewer_columns_than_expected_raises() -> None:
    with pytest.raises(GridGeometryError) as exc_info:
        read_grid_geometry(_grid_png(columns=4), expected_columns=COLUMN_COUNT)

    assert "column(s)" in str(exc_info.value)


def test_horizontally_scrolled_grid_raises() -> None:
    # Column N is no longer the Nth column, so measuring would be
    # confidently wrong rather than merely unavailable. Cropped just past
    # the first separator, and asked for a count the remaining columns do
    # satisfy, so this exercises the left-edge check specifically and not
    # the column-count one - which would otherwise pass it for the wrong
    # reason, since that message also mentions scrolling.
    scrolled = _cropped_from(_grid_png(), left=FIRST_SEPARATOR_X + COLUMN_WIDTH - 6)

    with pytest.raises(GridGeometryError) as exc_info:
        read_grid_geometry(scrolled, expected_columns=COLUMN_COUNT - 1)

    assert "left edge" in str(exc_info.value)


def test_separators_darker_than_the_threshold_are_columns() -> None:
    # Pins _LINE_THRESHOLD from below: a separator only just dark enough
    # still counts, so the constant cannot be quietly tightened.
    geometry = read_grid_geometry(_grid_png(line_colour=230), expected_columns=COLUMN_COUNT)

    assert len(geometry.columns) == COLUMN_COUNT


def test_separators_lighter_than_the_threshold_are_not_columns() -> None:
    # And from above: cell background and grid lines are told apart by
    # darkness, so a grid drawn in a pale enough grey has no measurable
    # columns at all rather than a plausible wrong answer.
    with pytest.raises(GridGeometryError):
        read_grid_geometry(_grid_png(line_colour=240), expected_columns=COLUMN_COUNT)


def test_a_blank_image_has_no_data_area() -> None:
    blank = Image.new("L", (WIDTH, HEIGHT), BACKGROUND)
    buffer = io.BytesIO()
    blank.save(buffer, format="PNG")

    with pytest.raises(GridGeometryError):
        read_grid_geometry(buffer.getvalue(), expected_columns=COLUMN_COUNT)
