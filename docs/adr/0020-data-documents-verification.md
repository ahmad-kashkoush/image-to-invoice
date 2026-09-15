# 0020. Verifying the saved Order and Invoice from Data > Documents

## Status

Accepted. Closes the last residual named in
[0004](0004-verification.md)'s Consequences, and `TODo.md`'s
"`Data > Documents` is unprobed" item.

## Context

Tasks 4.5 and 5.5 of the Task Description prescribe an independent second
look at what was saved:

> 4.5. Open Data > Documents and confirm one Order row with the generated
> number, expected Date and Cust.Ref., open state, and Total.
>
> 5.5. Open Data > Documents and confirm the Invoice row has the expected
> state and Total while the source Order remains open with the same
> Cust.Ref. and Total.

Neither was implemented. `verify_order_saved` and `verify_invoice_saved`
read the still-open editor's own fields back, which proves the widgets hold
what was typed - not that a row reached the database. ADR 0004 deferred this
explicitly because the screen had never been probed.

It has now been (`probes/probe-15-documents-list.txt`,
`probes/probe_documents_output/`). Four things it showed decided most of what
follows:

- The nav entry is a `Text` named `Documents`, like the four list screens
  already modelled, and it opens a single `Pane` named `Documents`. So far,
  the familiar shape.
- That pane is **not** just a grid. It also holds a document-type `Tree`
  (`Invoices > unpaid/paid`, `Orders > not shipped/shipped`) and a
  title/search strip, and **the tree scopes the search box**: typing
  `INV000002` with `Orders` selected returns no rows at all.
- The grid rows are UIA-invisible, as ADR 0004 predicted. Its columns are an
  unnamed icon column, `Document`, `Date`, `Name`, `Cust.Ref.`, `State`,
  `Total`, `Printed`, and a trailing filler - nine rendered columns measuring
  eight separator lines, with neither a pane border nor a leading grid edge.
- `Cust.Ref.` renders **clipped** on a default profile: a 17-character
  reference comes back as `WEB-2026-07...`.

## Decisions

**1. The Documents check is added to the editor read, not substituted for
it.** They fail differently and neither subsumes the other. The editor read
covers line items, Total Net, VAT and the payment fields, none of which the
Documents row shows; the Documents read covers the one thing the editor
cannot see, which is whether anything was persisted at all. Both feed the
same `problems` list so one `ManualReviewRequired` still carries the whole
picture for one save, per CLAUDE.md's aggregate-then-raise rule.

**2. The list-grid search moved down a layer, to
`ui_automation/list_grids.py`.** `verification` and `entity_resolution` are
peers that never import each other (ADR 0009), and this is the second caller
of a mechanism that lived inside one of them. `search_grid_exact`,
`_clipped_columns` and a new `open_list_screen` now sit next to the pixel and
screenshot code they are built on; `entity_resolution.resolver` re-exports
`search_grid_exact` so its four callers are untouched. `open_list_screen`
also replaces four textually identical private `_open_*_list` helpers.

**3. The Documents check runs last in each verify function, and restores the
editor in a `finally`.** Opening the list navigates away from the editor, and
Eclipse stops exposing an inactive tab's content to UIA - so every editor read
(including the vision items-grid read) has to happen first, and
`controls.reactivate_editor` has to run afterwards whether the check passed or
not, because the next workflow state drives that editor.

**4. The document-type tree node is selected explicitly before every
search.** Not cosmetic: the tree scopes the filter, so searching for an
Invoice number while `Orders` is selected returns nothing, which would read as
"the document was never saved" - a false failure that looks exactly like a
real one. Selecting the node also means a search can never return a document
of the wrong type.

**5. This grid opts out of ADR 0017's widen, and its clipped column is proven
by filtering instead.** `widen_column`'s arithmetic assumes a capture whose
separators start with a pane border and a grid left edge (`n + 2` lines, a
column's right edge at `separators[i + 2]`). This grid draws neither: 8 lines
for 9 columns. ADR 0017's own worst live failure came from acting on a
measurement shaped differently than expected - it resized the wrong column and
squeezed the one it was sent to fix - so the honest response is to refuse
rather than to add a second geometry to a fragile pixel model.

Instead, when `Cust.Ref.` comes back clipped, the check re-filters on the
document number **and** the full expected reference together. Fakturama's
search box ANDs whitespace-separated terms (probed:
`INV000002 WEB-2026-0714-A17` returns the row, `INV000002 WEB-2026-0714-A99`
returns nothing), so a single surviving row is exact evidence that the
document carries that reference - and it never depends on how wide a column
happens to be.

**6. Every comparison is made against a one-row read, and the document number
is compared with runs of zeros collapsed.** The first version of decision 5
matched the document number against a multi-row read of everything sharing the
reference, and the vision model transcribed `INV000002` as `INV0000002` in a
four-row capture while reading the same value correctly on its own. A long run
of zeros is exactly what this kind of read miscounts. Filtering to one row
first makes the model's job trivial and puts the discriminating work on
Fakturama's own filter.

One row makes that miscount rarer, not impossible: a live run on 2026-09-15
read `INV000007` as `INV0000007` in a **one-row** capture and stopped at
`verify_invoice_saved` on a document that had saved correctly. Nothing about
that comparison was load-bearing - the row was returned by Fakturama's own
filter on the number, which is the real evidence - so comparing the
transcription verbatim could only ever produce false failures. It is not
dropped entirely, because the search is a substring match and could in
principle return a different document (`PO000007` also matches a hypothetical
`PO0000070`); instead both sides are compared with runs of two or more zeros
collapsed to one. The single failure mode this read is known to have is
discarded; every other difference still fails closed.

**7. The State cell is compared as a word, not verbatim.** It renders an icon
plus a word, and the read transcribed the same paid Invoice as `paid` on one
pass and as a check-mark glyph followed by `paid` on the next. Comparing the
cell verbatim makes the check a coin toss; comparing the word is what it
actually means.

**8. Zero matching rows is a failure, never a skip.** The entire value of this
check is the case where the editor reads back perfectly and nothing was
written. A check that quietly passes when it finds nothing would invert its
own purpose.

**9. The Date check is deliberately partial, and says so.** Task 4.5 asks for
the "expected Date", but nothing writes the Order Date yet
(`populate_order_fields` writes only Cust.Ref.), so the row carries whatever
Fakturama proposed and comparing it to `order.order_date` would fail every
run. The check asserts the cell holds a readable date.
`comparisons.date_equals` already exists, unused, and drops in here in one
line when the write side lands.

**10. An unpaid Invoice's state word is not guessed.** No probed workspace has
ever contained one, so the word Fakturama renders for it is unknown. A paid
Invoice is compared against `paid` exactly; an unpaid one is asserted **not**
to read `paid`. That is the strongest claim the evidence supports, and a third
invented constant would pass silently when wrong.

## Consequences

- Tasks 4.5 and 5.5 are implemented. A run now confirms, from the saved
  document list rather than from the editor: the Order's number, a readable
  Date, its Cust.Ref., `open` state and Total; the Invoice's state and Total;
  and the source Order still `open` with the same Cust.Ref. and Total.

- **Verified live both ways on 2026-09-15.** A full workflow run reached
  `DONE` with exit 0 and no manual-review entry (`out/run18.log`), and a
  direct eight-case harness against the saved documents confirmed the check
  catches what it should: a wrong Cust.Ref., a wrong Total, a document number
  that does not exist, an Invoice that is paid when the order is not, and an
  Invoice number looked up as an Order. The happy path alone would not have
  distinguished any of those from an empty read.

- **Three extra list reads per workflow**, so roughly five more vision calls
  and ~35 seconds: one after the Order save, and two after the Invoice save
  (the Invoice row and the source Order row), plus a second read each time the
  clipped `Cust.Ref.` fallback fires - which on a default profile is every
  time. Worth revisiting alongside ADR 0019's similar note if per-order latency
  starts to matter.

- **The Documents list is left filtered** on the last key searched, and on the
  last tree node selected. Pre-existing behaviour for every other list screen
  this project drives, not made worse here, but now it applies to the screen a
  human is most likely to look at next.

- The unpaid-Invoice state check is weaker than the paid one until an unpaid
  Invoice is seen live. Tracked in `TODo.md`.

- `entity_resolution/config.py` lost `COLUMN_WIDEN_PIXELS` and
  `ui_automation/config.py` gained it, along with `LIST_GRID_SETTLE_SECONDS`
  and `LIST_GRID_TIMEOUT_SECONDS`, at identical values. Anyone overriding the
  old `FAKTURAMA_ENTITY_RESOLUTION_COLUMN_WIDEN_PIXELS` environment variable
  needs the `FAKTURAMA_UI_AUTOMATION_` name now.

- The move in decision 2 touches the path all four entity resolvers use. The
  MATCH branch of all four, plus the payment-standard read, was re-confirmed
  by the live run above (including a successful ADR 0017 widen of the Debtors
  grid's Company column). The **clean-profile CREATE branch was not re-run** -
  it needs a hand-configured fresh workspace - and no code inside those create
  paths changed, but that is an argument, not a measurement.
