# 0021. Measure the grid, not the pane it was captured in

## Status

Accepted. Amends the geometry half of
[0009](0009-refactoring-p0-boundaries.md) (which moved `grid_geometry` into
`ui_automation/`); unrelated to [0017](0017-widen-clipped-grid-columns.md),
which measures *list* grids for a different purpose.

## Context

A live run on 2026-09-15 stopped at `add_order_lines`:

```
grid screenshot shows 0 column(s), expected at least 10 -
the grid may be horizontally scrolled or clipped
```

The grid was neither scrolled nor clipped. `read_grid_geometry` decided that
a screenshot column is a separator if more than `_FULL_HEIGHT_FRACTION`
(0.9) of its pixels are dark, measured against **the height of the image it
was handed**. That image is `locators.items_grid_pane`'s capture, and that
pane holds more than the grid: under it sit a Notes box and the "Total Net"
field, 23px of a 128px pane. Every one of the ten real separators ran the
grid's full height and stopped there - 105 of 128 rows, 82% - so all ten were
rejected together. The single line that did clear 0.9 was the pane's own left
border at x=0, and one separator bounds zero columns.

The same capture then failed one step further in, on row lines. `_row_lines`
scanned down the column picked for rendering blank (`Picture`) and took a
dark pixel with light pixels two rows either side as a separator. The row the
product picker had just added was selected, and the selection highlight
filled that column solid (greyscale 95) - leaving one detectable line out of
four, where two are needed to measure a pitch. That defect predates this ADR
and was simply unreachable while the column check failed first.

Full measurements: `probes/probe_items_grid_output/`,
`spikes/uia_probe_items_grid_geometry.py`.

## Decisions

- **Find the grid's bottom edge first, and measure everything against it.**
  `_grid_bottom_band` scans up from the foot of the capture for the last line
  running the full width - the grid's own bottom border - and that becomes
  the height every later step divides by. The alternative on offer was
  lowering `_FULL_HEIGHT_FRACTION` to 0.8, which buys the same passing run
  and loses the check: a separator that stops a fifth short is the signature
  of a tooltip or a foreign window over the grid, which this module exists to
  catch. With the denominator corrected, the real separators measure 99-100%
  and the best false candidate falls from 62% to 53% - the constant stays at
  0.9 and discriminates better than before.

- **The bottom edge is a band, and it is not part of the lattice.**
  `_grid_bottom_band` returns the border's first *and* last row. The last is
  how tall the grid is; the first is where the row lattice stops. Counted as a
  lattice line, the border measures the pitch between the last row and itself
  - which is however much of that row the pane had room for, not a row
  height. Live, that is exactly what the first cut of this ADR did: pitches
  `[21, 25, 25, 25, 25]`, the 21 being a row clipped mid-height by the grid's
  own edge. The pitch check is kept exact (every gap equal) rather than
  relaxed to a majority: with the border excluded the remaining gaps *are*
  all equal, so a stray pitch again means something real is wrong.

- **Find row lines the same way, as full-width lines.** Not by scanning down
  a column believed to render blank. A row's selection highlight fills that
  column exactly as a separator would; what it does not do is span the full
  width of the grid. This also removes the module's dependence on a blank
  column existing, so `screens.ITEMS_GRID_BLANK_COLUMN` is deleted rather
  than left to document an approach no longer taken.

- **A capture with no full-width line is not a grid.** That is the new
  failure when the region is blank or occluded, and it is reported as such
  ("does not look like a grid") instead of as a column count, so the next
  occurrence names the right cause.

- **Keep both thresholds at 0.9, and keep them separate.**
  `_FULL_WIDTH_FRACTION` is not 1.0 because a vertical scrollbar interrupts a
  row line's right end once the grid holds more rows than fit.

## Consequences

- The measurement no longer depends on the pane locator returning the grid
  and nothing else. `items_grid_pane` picks a sibling by position, so what it
  returns has changed with layout before and can again; the grid is now found
  within whatever that pane contains.

- A grid whose header strip is its only full-width dark band (no bottom
  border drawn) measures its header as the whole grid and fails in
  `_header_bottom` with "no data area below its header strip". Fail-closed,
  but under a message that points at the header rather than at the missing
  border. Not seen live; the Items grid draws the border.

- An Items grid with **no rows at all** now fails with "no row separators -
  cannot measure row height" rather than returning a guessed pitch: an empty
  grid draws its header line and its border and nothing between them, so
  there is no lattice to measure. Captured live
  (`probes/probe_items_grid_output/`, an empty editor: full-width lines at 0,
  26 and the 47..49 border). Nothing in the flow measures an empty grid -
  `fill_and_verify_line` runs after the picker has added a row - so this is a
  guard, not a path.

- The existing pure-logic tests in `tests/ui_automation/test_grid_geometry.py`
  still hold unchanged, including every fail-closed path - verified by calling
  `read_grid_geometry` directly against that file's synthetic grid, not by
  running the suite (this project verifies live).

- Three of the four faults this module has produced live - "8 of 10 columns"
  from a tooltip, "8 of 10" from an occluding editor, and this one - were the
  same shape: something that is not the grid inside the thing being measured.
  The retry loop in `items_grid._measure_grid` addresses the two transient
  ones. This addresses the one that never goes away on a retry, which is why
  all three attempts failed identically.
