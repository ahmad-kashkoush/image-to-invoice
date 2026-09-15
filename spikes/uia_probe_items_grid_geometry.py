"""Standalone, live probe: why `grid_geometry.read_grid_geometry` reports
0 columns for the Order's Items grid.

Background: a live run on 2026-09-15 stopped at `add_order_lines` with
"grid screenshot shows 0 column(s), expected at least 10". Zero is the
telling number: a horizontally scrolled or clipped grid still shows *some*
full-height separators, so zero means either the captured region is not the
grid at all (occlusion, a stale rectangle from a tab that was navigated
away from), or no separator clears `_FULL_HEIGHT_FRACTION` - e.g. a
horizontal scrollbar now eats the bottom of the pane, which would be a
threshold effect rather than a wrong region.

Unlike the other spikes/ scripts this one imports the project, on purpose:
the point is to measure exactly what `orchestrator.steps.items_grid._measure_grid`
measures, through the same locator, not an independent re-implementation.

Usage (on the Windows machine, with Fakturama running):
  1. Leave the Order editor on screen with its Items grid visible - ideally
     in the state the failing run left behind (product picked, line added).
  2. py spikes/uia_probe_items_grid_geometry.py
     (no shell redirection needed - it writes its own UTF-8 report.txt)

Output: a plain-text report to stdout (redirect to a probes/ file, e.g.
`> probes/probe-16-items-grid-geometry.txt`) plus PNGs under --outdir
(default: probes/probe_items_grid_output/): the pane capture itself and,
for comparison, a capture of the whole main window.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fakturama_automation.ui_automation import screens  # noqa: E402
from fakturama_automation.ui_automation import controls, grid_geometry, locators  # noqa: E402
from fakturama_automation.ui_automation.app import FakturamaApp  # noqa: E402

# The fractions swept below _FULL_HEIGHT_FRACTION: if separators appear at a
# lower one, the region is the grid and only the threshold is wrong.
FRACTIONS = [0.9, 0.85, 0.8, 0.7, 0.6, 0.5, 0.3]


class _Tee:
    # PowerShell's `>` writes UTF-16, which made the first report awkward to
    # read back; the probe writes its own UTF-8 copy instead.

    def __init__(self, path: Path) -> None:
        self._file = path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        sys.__stdout__.write(text)
        self._file.write(text)

    def flush(self) -> None:
        sys.__stdout__.flush()
        self._file.flush()


def _rect(control) -> str:
    r = control.rectangle()
    return f"({r.left},{r.top})-({r.right},{r.bottom}) {r.width()}x{r.height()}"


def _dark_runs(pixels, width: int, height: int, threshold: int) -> list[tuple[int, int]]:
    # (x, count of pixels under `threshold` in that screenshot column).
    return [
        (x, sum(1 for y in range(height) if pixels[x, y] < threshold))
        for x in range(width)
    ]


def _report_image(image: Image.Image, label: str) -> None:
    grey = image.convert("L")
    width, height = grey.size
    pixels = grey.load()
    print(f"\n--- {label}: {width}x{height} ---")

    values = list(grey.getdata())
    print(f"brightness: min={min(values)} max={max(values)} mean={sum(values) / len(values):.1f}")
    if min(values) >= grid_geometry._LINE_THRESHOLD:
        print(
            f"NO pixel is under _LINE_THRESHOLD ({grid_geometry._LINE_THRESHOLD}) - "
            "this capture is blank: the region is occluded or not the grid"
        )
        return

    runs = _dark_runs(pixels, width, height, grid_geometry._LINE_THRESHOLD)
    tallest = sorted(runs, key=lambda pair: pair[1], reverse=True)[:14]
    # first/last dark y matter as much as the count: a separator that runs
    # from the top and stops short of the bottom is being cut off by
    # something drawn there (a horizontal scrollbar), which is a different
    # fault from a region that is not the grid at all.
    print("tallest dark columns (x, dark px, % of height, first..last dark y):")
    for x, count in sorted(tallest):
        dark_ys = [y for y in range(height) if pixels[x, y] < grid_geometry._LINE_THRESHOLD]
        span = f"{dark_ys[0]}..{dark_ys[-1]}" if dark_ys else "-"
        print(f"  x={x:4d}  {count:4d}  {100 * count / height:5.1f}%  {span}")

    # A band of rows at the bottom that no candidate separator reaches is the
    # signature of a scrollbar appearing since the columns were widened.
    bottom_dark = [
        y for y in range(height)
        if sum(1 for x in range(width) if pixels[x, y] < grid_geometry._LINE_THRESHOLD) > width * 0.5
    ]
    print(f"rows that are >50% dark: {len(bottom_dark)} of {height}")

    print("columns detected per full-height fraction:")
    for fraction in FRACTIONS:
        separators: list[int] = []
        for x, count in runs:
            if count > height * fraction and (
                not separators or x > separators[-1] + grid_geometry._MIN_SEPARATOR_GAP
            ):
                separators.append(x)
        columns = max(len(separators) - 1, 0)
        marker = "  <- _FULL_HEIGHT_FRACTION" if fraction == grid_geometry._FULL_HEIGHT_FRACTION else ""
        print(
            f"  {fraction:.2f}: {len(separators):3d} separator(s) = {columns:3d} column(s)"
            f"{marker}"
        )

    print(
        f"expected columns: {len(screens.ITEMS_GRID_RENDERED_COLUMNS)} "
        f"({', '.join(screens.ITEMS_GRID_RENDERED_COLUMNS)})"
    )

    # The row lattice, and where the grid's own bottom border sits in it. A
    # stray short pitch at the end is the border being counted as a row line;
    # the border is several pixels thick and sits an arbitrary distance under
    # the last row, because the pane clips the grid mid-row.
    full_width = [y for y in range(height) if grid_geometry._is_full_width_line(pixels, width, y)]
    print(f"full-width lines: {full_width}")
    try:
        band = grid_geometry._grid_bottom_band(pixels, width, height)
    except Exception as exc:  # noqa: BLE001 - the probe reports, it does not handle
        print(f"bottom border: NOT FOUND ({exc})")
        return
    print(f"bottom border band: {band[0]}..{band[1]}")
    lattice = [y for y in full_width if y < band[0]]
    print(f"row lines (border excluded): {lattice}")
    print(f"pitches: {[b - a for a, b in zip(lattice, lattice[1:])]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="probes/probe_items_grid_output")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sys.stdout = _Tee(outdir / "report.txt")

    app = FakturamaApp()
    app.connect(screens.APP_TITLE_RE)
    main_window = app.main_window()
    print(f"main_window: {_rect(main_window)}")

    # Without these two the capture is of whatever is drawn on top - the
    # first run of this probe photographed VS Code. The real code calls both
    # before every capture (items_grid._measure_grid); so does this.
    controls.focus_foreground(main_window)
    controls.move_pointer_away(main_window)

    main_image = main_window.capture_as_image()
    main_path = outdir / "main_window.png"
    main_image.save(main_path)
    print(f"saved {main_path}")

    items_label = None
    try:
        grid_pane = locators.items_grid_pane(main_window, items_label=items_label)
    except Exception as exc:  # noqa: BLE001 - the probe reports, it does not handle
        print(f"items_grid_pane FAILED: {type(exc).__name__}: {exc}")
        print("the Order editor is not the active tab - nothing to measure")
        return

    print(f"items grid pane: {_rect(grid_pane)}  control_type={grid_pane.element_info.control_type}")
    pane_rect = grid_pane.rectangle()
    win_rect = main_window.rectangle()
    if (
        pane_rect.left < win_rect.left
        or pane_rect.top < win_rect.top
        or pane_rect.right > win_rect.right
        or pane_rect.bottom > win_rect.bottom
    ):
        print("WARNING: the pane's rectangle is not inside the main window's - stale or off-screen")

    controls.focus_foreground(main_window)
    controls.move_pointer_away(main_window)
    pane_image = grid_pane.capture_as_image()
    pane_path = outdir / "items_grid_pane.png"
    pane_image.save(pane_path)
    print(f"saved {pane_path}")

    _report_image(pane_image, "items grid pane capture")

    buffer = io.BytesIO()
    pane_image.save(buffer, format="PNG")
    try:
        geometry = grid_geometry.read_grid_geometry(
            buffer.getvalue(), expected_columns=len(screens.ITEMS_GRID_RENDERED_COLUMNS)
        )
    except Exception as exc:  # noqa: BLE001 - the failure is the result
        print(f"\nread_grid_geometry: {type(exc).__name__}: {exc}")
        return
    print(f"\nread_grid_geometry OK: {geometry}")


if __name__ == "__main__":
    main()
