# 0017. Widen a list grid's clipped column before matching on it

## Status

Accepted. Completes what [0014](0014-debtor-matching-by-customer-id.md)
set out to do.

## Context

ADR 0014 replaced the Debtor identity with a real Customer ID and introduced
a five-field match (Company, First Name, Name, ZIP, City) read from the
Debtors list grid. It explicitly assumed that grid did *not* clip its cells -
`TODo.md`'s picker item records the Company column as "confirmed to render
clipped (unlike the Debtors list grid `resolve_debtor` searches)".

That assumption was wrong, and it is why the duplicate-Debtor bug survived
0014. Live on 2026-09-15 the grid returned:

```
{'No.': 'CUST000001', 'First Name': 'Marta', 'Name': 'Klein',
 'Company': 'Northstar Offic...', 'ZIP': '10117', 'City': 'Berlin'}
```

`matching.exact_debtor_matches` compares Company by exact equality, so
`'Northstar Offic...' == 'Northstar Office GmbH'` is false, no row ever
matches, and `resolve_exact_or_create` takes the create branch every single
run. Nine identical Northstar Debtors is what that looks like after nine
runs.

What makes this nasty is that it is not deterministic across profiles.
Column widths are persisted per profile in `fakturamaviews.properties`, so
the same code matched correctly on one workspace and silently duplicated on
another - which is exactly what happened here, twice, within an hour.

These grids are custom-rendered: probed live, the Debtors grid's entire UIA
subtree is six unnamed Panes, two Texts and the search Edit. There is no
Header, HeaderItem or DataGrid, so a column cannot be measured or resized
through UIA. It *can* be resized with the mouse - the app shows a `SIZEWE`
cursor over a header separator.

## Decisions

- **Detect clipping, do not assume it.** `grid_columns.is_clipped` tests for
  a trailing ellipsis (the real glyph `…` and the `...` a vision read usually
  transcribes). `resolver.search_grid_exact` reads the grid, and only if a
  column it was asked to read comes back clipped does it widen and re-read,
  once. A grid whose columns are already wide enough is never touched.

- **Measure the columns from pixels, over the grid's empty rows.** Cell text
  contributes nothing there, which matters: a mean-brightness test over rows
  *with* text mistook a glyph edge for a separator and measured one at x=9.
  A separator is a line, so the test is that nearly every pixel down the band
  is off-white.

- **Ask the app where the drag handle is, do not compute it.**
  `_resize_handle_y` hovers down the header strip and returns the y where the
  cursor becomes `SIZEWE`. A pixel heuristic for "where is the header" picked
  the pane border instead (y=6 for a header at y=56) and dragged in the
  search row - which is silent, because the drag simply does nothing.

- **Refuse to act on a measurement that does not add up.** An n-column grid
  measures exactly n + 2 separator lines. A measurement that merges two lines
  (a column narrower than the 30px minimum) or misses the last one shifts
  every index after it, and the drag then resizes a *different* column than
  asked - live, that squeezed Company to 25px and gave the space to ZIP,
  which is worse than the clipping it was sent to fix. The count is checked
  exactly and the function returns False rather than guess.

- **Budget the drag against the space to the right.** A column that has been
  pushed off the visible area is worse than a clipped one - it reads as
  empty, and an empty cell fails the same exact-match comparison while giving
  no hint why. Live, an unbudgeted widen pushed ZIP and City off the Debtors
  grid entirely. The widen is also done once, not once per clipped column.

- **Failing to widen is not fatal.** `widen_column` returns False and the
  caller returns the rows it already has. The exact-match comparison then
  fails closed exactly as it did before this ADR - the pre-existing
  behaviour, not a new failure mode.

## Consequences

- `resolve_debtor` matches. Across eight live runs on 2026-09-15 the database
  holds exactly one Northstar contact (`CUST000001`). The duplicate-Debtor
  bug is closed - by this, not by 0014 alone.

- Every caller of `search_grid_exact` gets this: Debtors, Products, VAT rates
  and payment methods. Only the Debtors grid has been seen to clip, but the
  Products grid matches on a SKU that could equally outgrow its column.

- **This mutates the user's UI.** A run can leave a column wider than it found
  it, and that change is persisted to the profile. It is deliberate - the
  alternative is a pipeline that silently creates duplicates - but it means
  the automation is no longer purely read-only with respect to layout.

- The ellipsis test depends on a vision model transcribing the glyph. A model
  that renders a clipped cell some other way (or silently drops the ellipsis)
  would defeat the detection, and the failure mode is the old one: a
  duplicate. The stronger version of this check would compare the cell's
  pixel width against its text, which is not worth building until it breaks.

- `orchestrator/steps/pickers.py` still matches on row count rather than
  identity, for the same clipped-Company reason that motivated this ADR. It
  could now use the same widen-and-compare treatment; that remains open in
  `TODo.md`.
