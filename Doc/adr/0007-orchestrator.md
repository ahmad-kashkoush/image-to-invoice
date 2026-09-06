# 0007. Orchestrator (Section 7)

## Status

Accepted

## Context

The orchestrator is the integration point tying the five already-implemented
components (extraction, normalization, entity resolution, verification,
error handling) into the single `discover -> act -> verify -> advance` state
machine `Doc/Design.md`'s Workflow & Verification section describes. Every
section it composes is real and independently unit-tested; the scaffold
(`orchestrator/state_machine.py`) already specified the 9-state sequence and
a `WorkflowState` enum, leaving `run_workflow` itself to implement.

Two things do not have an "obviously correct" answer dictated by the design
doc or the task description:

1. Several Order-editor **write actions** the state machine must perform -
   entering a line into the order's own item grid, attaching an
   already-resolved Debtor/Payment Method to the order, creating the linked
   Invoice via Data > Documents, and applying payment - have no VM probe at
   all (`TODo.md`'s "Not started" section), unlike every *read-back*
   selector `verification/config.py` already pins.
2. `run_workflow` must catch failures from every section it composes, not
   only its own; `entity_resolution`/`verification` raise
   `ManualReviewRequired` themselves, but a raw `ui_automation.controls`
   lookup failure (`ControlNotFoundError`/`AmbiguousControlError`) is a
   different exception type that has never before needed to cross a
   section boundary into `error_handling`.

## Decisions

**1. Ship all 9 states now, with un-probed write actions as explicit
empty-string `# TODO probe` placeholders, rather than blocking the whole
section on a VM probe session.** This is the same convention
`verification/config.py` already established for the Invoice editor's
payment fields (`Doc/adr/0004`): a lookup against a real window fails closed
(`ControlNotFoundError`/`AmbiguousControlError`) instead of guessing a
selector that might silently target the wrong control. The alternative -
only implementing states 1-3 (EXTRACT/NORMALIZE/OPEN_ORDER) until a probe
exists - would leave the state machine itself, and its
`ManualReviewRequired`-catching contract, untested until then. Shipping the
full loop now means the *control flow* is proven today, and a future probe
session only needs to fill in `orchestrator/config.py`'s placeholders, not
restructure the loop.

**2. `orchestrator/actions.py` holds every UI write action, separate from
`state_machine.py`'s loop.** Mirrors the split `entity_resolution.resolver`
already draws between the search-then-create decision
(`resolve_exact_or_create`) and the control-driving half
(`search_grid_exact`): the state loop reads as control flow (state, action,
verify, advance) with the UI mechanics factored out, rather than each state
inlining several `controls.find_control` calls.

**3. `ui_automation.controls.find_control`'s exceptions
(`ControlNotFoundError`, `AmbiguousControlError`, and
`ui_automation.waits`' `DialogTimeoutError`) are caught at the same loop
boundary as `ManualReviewRequired` and converted to
`ManualReviewRequired(state.value, str(error))`.** Before the orchestrator
existed, these exceptions only needed to propagate as far as whatever test
or caller directly exercised `ui_automation`/`entity_resolution` - they never
had to cross into `error_handling`. `Doc/Design.md`'s own control-discovery
section already treats an unresolvable or ambiguous control as "stops for
manual review", so this conversion is the orchestrator's job, not a change
to `ui_automation.controls` itself (which still just raises the specific
exception; it is not `error_handling`-aware and should not become so). A
`ManualReviewRequired` raised by a downstream section keeps its own `step`
(e.g. `"resolve_debtor"`) unchanged - only a bare UI-discovery exception gets
relabeled with the current `WorkflowState`.

**4. `ui_automation.app.FakturamaApp` is imported inside `run_workflow`'s
body, not at module level.** `state_machine.py` needs it only to
default-construct `app` when a caller does not supply one (every test
supplies a fake). Importing it at module level would transitively import
`pywinauto.Application`, which fails immediately off Windows (`Doc/adr/0002`)
- that would make the whole `orchestrator` package, including
`WorkflowState` and every test seam, unimportable on macOS/Linux, undoing
the cross-platform testability every prior section preserved. This was
caught by actually running the test suite cross-platform, not by inspection
- see Consequences.

**5. `run_workflow` returns the `WorkflowState` last reached (`DONE` on
success), not `None`, despite the original stub's `-> None` signature.**
`route_to_manual_review` never raises and never returns anything a caller
could inspect, so without a return value a test (or a future caller) has no
way to tell how far a run got except by parsing the manual-review queue
file. Returning the enum costs nothing and makes both the tests and any
future caller simpler.

**6. Tests cover three distinct propagation paths, not a full
extract-to-`DONE` run.** A true end-to-end happy-path test would need a
single fake vision client correctly answering every vision call in the
whole run (extraction's `record_order`, every entity-search grid read, the
order/invoice item-grid read-backs) in the right sequence, plus a fake `app`
wired for every control lookup across four entity resolvers and three
verification functions - a large amount of scaffolding for marginal
additional confidence, given every section it would exercise already has
its own unit tests. Instead, `tests/orchestrator/test_state_machine.py`
proves: a `normalization` failure stops before any UI action; a control
lookup failure (`AmbiguousControlError`) is converted to
`ManualReviewRequired` at the loop boundary; and a downstream section's own
`ManualReviewRequired` (entity resolution's ambiguous-match rule) passes
through with its original `step` intact. Each is read back from the
manual-review queue file, since `run_workflow` never lets a
`ManualReviewRequired` escape to its caller.

**7. `populate_order_fields`'s Debtor-attachment probe (2026-09-06) landed
three decisions, once a live VM session actually opened the customer field:
a wrong-assumption removal, a new fallback for one specific kind of window,
and a deliberately weaker match check.**

- The Order screen has no Payment Method field at all - confirmed live by
  searching every Text control in the New Order editor for "payment" (only
  the left-nav "terms of payment" link matches). `ORDER_PAYMENT_METHOD_FIELD_AUTO_ID`
  and its `set_text()` call are deleted, not filled in; Payment Method is
  attached later at the Invoice stage by `apply_payment`, unchanged.
  `resolve_payment_method` is still called from `populate_order_fields` so
  the record exists in Fakturama by then, even though nothing on the Order
  screen reads its result.
- The customer field turned out to be a big multi-line address `Edit`, not
  a plain text box - `ORDER_CUSTOMER_FIELD_AUTO_ID` was never going to work
  regardless of what auto_id a probe found. Attaching a Debtor means
  clicking a small blank-named `Image` to its left (located structurally,
  as the Image immediately following the "Addresses" label in their shared
  parent Pane), which opens a **genuinely separate top-level OS window**
  ("Select the address") - confirmed via raw window enumeration, not a
  combo-style popup rendered inside the main window's own screenshot
  bounds the way `entity_resolution.combos` handles VAT/Country. Neither
  `Application.window(title_re=...)` (this app's own connected process)
  nor a fresh `Desktop(backend="uia").windows()` scan reliably found this
  dialog while it was visibly open on screen; raw `win32gui.EnumWindows`
  did, every time. `ui_automation.app.FakturamaApp.top_level_window_by_title`
  wraps that fallback, isolated to the one module that already owns every
  other pywinauto-specific mechanism (`Doc/adr/0002`) - it is not a
  replacement for `window()`/`waits.wait_for_dialog`, which keep working
  for every other dialog in this codebase.
- That dialog's grid is read the same way every other list/search grid is
  (`ui_automation.vision_grounding`), extended with a new
  `read_grid_rows_located` (rows + bounding boxes, mirroring
  `read_combo_options`) since this caller, unlike every other grid reader,
  has to click the one matched row. Its own match check is deliberately
  **not** an exact text-equality check against the target company name the
  way every other resolver's search is
  (`entity_resolution.matching.exact_text_matches`): confirmed live that
  this grid's Company column can render too narrow to show the full value
  (a real "Northstar Office GmbH" row read back visibly clipped to "thstar
  Office ..."), so a text-equality check against the untruncated target
  could never pass even for the correct row. It requires exactly one row
  after searching by company name instead, trusting Fakturama's own Search
  filtering (confirmed live: it did not also surface an unrelated row
  containing a similar substring in a different column) rather than
  independently verifying it - a narrower guarantee than the rest of this
  codebase's search-then-verify pattern, accepted here because the
  alternative (matching by the Debtor's own unique No./Customer ID, which
  doesn't get clipped) needs `entity_resolution.debtor.resolve_debtor` to
  expose that identifier first, which is out of this task's scope - see
  `TODo.md`'s Future work.
- Separately (found while verifying the above, not part of the original
  gap): `entity_resolution.debtor`'s Company field needed
  `ui_automation.controls.type_text` (real keystrokes) instead of
  `set_text()` - confirmed live, isolated field-by-field, that `set_text()`
  silently failed to persist Company through Save specifically (it read
  back correctly right up until the Save click, then came back empty every
  time, while Street/ZIP/City/First/Last Name all persisted fine with
  `set_text()` on the same form). This points to UIA `SetValue` not firing
  whatever modify event Fakturama's save-binding listens for on that one
  field; real keystrokes fixed it in the same live test. Not a blanket
  replacement - every other confirmed-working `set_text()` call site is
  unchanged.

**8. `add_order_line`'s live "duplicates the same line item, then errors"
bug (2026-09-06) traced to two independent, real defects, not to the
suspected Fakturama-process-degradation explanation Decision 7's session
left open - both fixed and confirmed live.**

- `entity_resolution.vat_rate._create_vat_rate`'s "Value" field defaults to
  a pre-filled "0%", unlike every other field this module's create-forms
  fill (which start blank) - plain `controls.type_text` (click + type, no
  clear) inserts into that existing text instead of replacing it. Confirmed
  live via a saved record's own edit form: Name persisted correctly ("19%")
  while Value silently stayed "0%" regardless of what was typed. Since
  `resolve_vat_rate`'s search matches by that same Value column, this meant
  it could never find its own previously-created rate on a later lookup,
  creating a fresh duplicate "19%"/Value-0% record every time a new Product
  needed that VAT percent. Fixed by clearing the field (`Ctrl+A`+`Delete`)
  before typing and committing with a trailing `Tab` - the same idiom
  `_fill_grid_text_cell` already uses for the Items grid's own cells, not a
  new pattern.
- The "Select a product" picker can auto-confirm and close itself the
  instant its search box narrows to exactly one matching row, entirely on
  its own - before this codebase's row-click-then-OK sequence ever runs.
  This looks identical, from the caller's side, to the flash-open-close
  race Decision 7's session (and the history in `TODo.md`) already fixed
  retries for: the dialog is unexpectedly gone and the next `find_control`
  call fails. But it is not the same event - it is a *successful* add, not
  a crash - and the old retry logic had no way to tell the two apart, so it
  reopened the picker and re-added the same row on every attempt that hit
  this. Confirmed live with instrumentation on every internal step: across
  3 retry attempts none reported successfully clicking a row, yet the Items
  grid showed 3 duplicate rows of the same SKU afterward. Fixed:
  `_pick_single_row_in_dialog` now checks whether the dialog still exists
  immediately after typing, before trying to re-find its "Search:" box, and
  returns early (nothing left to click) if it's already gone. The
  existence check itself needed a small additional fix - a new
  `_dialog_still_exists` helper, since `dialog.exists()` on an
  already-destroyed handle-based wrapper can raise a raw `_ctypes.COMError`
  ("An event was unable to invoke any of the subscribers") instead of
  returning `False`, confirmed live; the helper treats that COMError as
  "gone" too, the same class of transient UIA/COM hiccup
  `controls.find_control` already tolerates rather than propagates.

Both fixes were found and verified using a live Fakturama instance
connected to directly (not a scripted VM session) - a useful reminder that
this class of bug (a duplicate-add loop, a silently-wrong saved field) is
often invisible from code review alone and needs exactly this kind of
live, instrumented reproduction to actually pin down, matching this
project's own "verify live on the VM" testing convention.

## Consequences

- The Order-editor write actions gated on a VM probe
  (`ORDER_CUSTOMER_FIELD_AUTO_ID`, `ORDER_PAYMENT_METHOD_FIELD_AUTO_ID`,
  `ORDER_LINE_ADD_BUTTON_TITLE`, `INVOICE_FROM_ORDER_BUTTON_TITLE`,
  `INVOICE_EDITOR_PANE_NAME`) will fail closed against a real Fakturama
  window today, stopping at `POPULATE_ORDER_FIELDS`/`ADD_ORDER_LINES`/
  `CREATE_AND_VERIFY_INVOICE` respectively - this is expected, not a
  regression, until a VM probe session fills them in (`TODo.md`'s "Not
  started" section still applies).
- Because the full happy path (reaching `WorkflowState.DONE`) is not
  exercised by a test, a future VM probe session that fills in the
  placeholders above should be paired with a live-VM smoke run of the CLI
  (`python -m fakturama_automation.orchestrator <image_path>`) against a
  real order, not assumed correct from unit tests alone.
- `orchestrator/actions.py`'s `apply_payment` does not re-invoke
  `entity_resolution.payment_method.resolve_payment_method` a second time
  (only `populate_order_fields` resolves it, when attaching to the Order);
  it only sets the Invoice's payment-method control directly. If a future
  probe finds the Invoice's payment method is not simply inherited from the
  Order and needs its own independent resolution, this will need revisiting.
