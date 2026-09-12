# Implementation notes

What was actually decided while building the system, and why — as distinct
from [Design.md](Design.md), which describes the intended architecture. Each
section covers one module or workflow state, oldest first. These are the
notes referenced by `CLAUDE.md`'s per-section wrap-up ritual; the decisions
that needed a fuller write-up have their own ADR under [adr/](adr/).

## `orchestrator/actions.py::populate_order_fields` — attaching a resolved Debtor to the Order

- The Order's customer field is a large multi-line address `Edit` under the "Invoice address" tab, not a plain text box - it can't be filled directly the way Cust.Ref. is. Attaching a Debtor instead means clicking a small blank-named `Image` just to that Edit's left (located structurally, as the Image immediately following the "Addresses" label in their shared parent Pane, since it carries no accessible name and its `auto_id` is session-unstable like every other blank-named control in this app), which opens a genuinely separate top-level OS window titled "Select the address" - confirmed live via raw window enumeration, not a combo-style popup rendered inside the main window's own screenshot bounds the way `entity_resolution.combos` handles VAT/Country selection. `ui_automation.app.FakturamaApp.top_level_window_by_title` exists specifically for this: pywinauto's own window enumeration (`Application.window(title_re=...)`, a fresh `Desktop(backend="uia").windows()` scan) does not reliably find this particular dialog even while it is visibly open on screen, but raw `win32gui.EnumWindows` does.
- That dialog's results grid is searched and read the same way every other list/search grid in this app is (typing into "Search:", reading the UIA-invisible grid back via `ui_automation.vision_grounding`), but unlike those callers, this one also has to click the single matched row (there is no keyboard-select equivalent verified here) - `vision_grounding.read_grid_rows_located` extends the existing row-reading pattern with a bounding box per row, mirroring how `read_combo_options` already locates combo entries for `entity_resolution.combos`' own coordinate clicks.
- This picker's own exact-match check deliberately does not compare cell text against the target company name the way every other resolver's search does: confirmed live that its Company column can render too narrow to show the full value (a real "Northstar Office GmbH" row read back visibly clipped to "thstar Office ..."), so a text-equality check against the untruncated target could never pass even for the correct row. Instead it requires exactly one row after searching by company name, trusting Fakturama's own Search filtering (confirmed live: it did not also surface an unrelated row with a similar substring in a different column) rather than independently verifying it - a narrower guarantee than the rest of this codebase's search-then-verify pattern. See `Doc/adr/0007-orchestrator.md` and `TODo.md`'s Open list for the more correct fix (match by the Debtor's own unique No./Customer ID instead, once resolution exposes it).
- Separately, `entity_resolution.debtor`'s Company field needed `ui_automation.controls.type_text` (real keystrokes) instead of `set_text()` (UIA `SetValue`): confirmed live that `set_text()` silently failed to persist Company through Save specifically - the value read back correctly right up until the Save click, then came back empty, while every other field on the same form (Street, ZIP, City, First/Last Name) persisted correctly with `set_text()`. This points to `SetValue` not firing whatever modify event Fakturama's save-binding listens for on that one field; real keystrokes fixed it. Not a blanket replacement - every other confirmed-working `set_text()` call site is unchanged.

## `orchestrator/actions.py::_open_picker_dialog` / `_pick_row_via_picker` — the "Select a product"/"Select the address" dialogs (2026-09-06)

- Both pickers are separate top-level OS windows, and both can open and vanish again within a fraction of a second of the toolbar click that opens them (root cause not isolated; most likely an input race between the click and the dialog's own initial render/focus). This surfaced as `no Text control named 'Search:' ... found within 5.0s` *after* `app.top_level_window_by_title` had already reported the dialog present - observing the window once is not evidence it is still there a moment later. Three rounds of fix, each of which the next proved insufficient: (1) `top_level_window_by_title` now collects every matching visible window and raises `AmbiguousControlError` on more than one, mirroring `controls.find_control`'s convention instead of silently taking the first (a stale leftover picker could otherwise be grabbed); (2) `_open_picker_dialog` re-checks `top_level_window_is_open` after a stabilize delay and probes for the dialog's own "Search:" content, re-clicking up to `DIALOG_OPEN_ATTEMPTS` times; (3) the dialog can vanish even after content is confirmed present, so `_pick_row_via_picker` wraps the entire open-search-pick cycle as one retryable unit, pressing Escape first so a retry's `top_level_window_by_title` can't collide with a stray leftover.
- What this cost, and why it is recorded rather than trimmed: an extended live session (dozens of scripted open/close cycles against one Fakturama process) showed the failure rate apparently *worsening* over time, with no code-observable difference between an instant success and three failed retries in a row - ruled out by direct experiment were focus theft, `set_focus()`, repeated UIA tree queries, and a 3s cool-down between attempts. That looked like the live Fakturama process degrading. It was not: the real causes were the two bugs in the next note, both of which reproduce cleanly on a freshly restarted process. "The app under test is flaky" is the explanation to reach for last.
- Related, same root shape: `entity_resolution.combos._read_open_combo_options` screenshotted the Country combo with no settle delay between opening/type-ahead-scrolling it and the capture, and the vision read came back with nonsense options (`['all', 'andy']` for a list that should contain "Germany"), failing the order closed. Capturing a control mid-open is a far likelier explanation than a vision model inventing nonsense from real country names. Every other UI-changing-then-reading step in this codebase already slept first; these now take the same `settle_seconds` keyword, defaulting to the same `SEARCH_SETTLE_SECONDS` constant `resolver.search_grid_exact` uses.

## `orchestrator/actions.py::add_order_line` — root-causing the "adds the same line item multiple times" live bug (2026-09-06)

- `entity_resolution.vat_rate._create_vat_rate`'s "Value" field defaults to a pre-filled "0%", not blank like every other field this module fills - typing into it without first clearing (the same `click_input()` + `type_keys()` pattern used everywhere else) inserts into that existing text rather than replacing it. Confirmed live via a saved record's own edit form: Name persisted correctly ("19%") while Value silently stayed "0%" regardless of what was typed. Since `resolve_vat_rate`'s search matches by that same Value column, this meant the resolver could never find its own previously-created rate on a later lookup, creating a fresh duplicate "19%"/Value-0% record every time a new Product needed that VAT percent - the underlying cause of the product catalog accumulating enough duplicate data over repeated runs to eventually destabilize the "Select a product" picker (see the next note). Fixed by clearing the field (`Ctrl+A`+`Delete`) before typing and committing with a trailing `Tab`, the same idiom `_fill_grid_text_cell` already uses for the Items grid's own cells.
- The "Select a product" picker (opened from the Items toolbar's first Image, structurally identical to `_attach_debtor_to_order`'s "Select the address") can auto-confirm and close itself the instant its search box narrows to exactly one matching row, entirely on its own - before this codebase's own row-click-then-OK sequence ever runs. Confirmed live with instrumentation on every internal step: across 3 retry attempts, none reported successfully clicking a row, yet the Items grid showed 3 duplicate rows of the same SKU afterward - proving the dialog's self-close-on-typed-exact-match was itself already a successful add each time, not the flash-open-close race the dialog-open retry logic above was built to handle. The old code had no way to distinguish "closed because it already succeeded" from "closed because it crashed", so its retry loop reopened the picker and re-added the row on every attempt that hit this. Fixed: `_pick_single_row_in_dialog` now checks whether the dialog still exists immediately after typing (before trying to re-find its "Search:" box) and returns early - nothing left to click - if it's already gone, via a `_dialog_still_exists` helper that also treats a raw `_ctypes.COMError` from re-resolving an already-destroyed window handle as "gone" rather than letting it propagate (confirmed live this can happen on `dialog.exists()` itself). Confirmed fixed end-to-end on a freshly restarted Fakturama process: a two-line order added both lines exactly once each, correct quantities/VAT/totals, no manual-review entry.

## `SAVE_AND_VERIFY_ORDER` — three bugs in the first full run that reached it (2026-09-06)

- **Every order-level field read back its own label, not its value.** `readback.read_field_text` used `control.window_text()`; pywinauto's uia `EditWrapper` does not override it, so it resolves to `UIAElementInfo.rich_text`, which asks for the TextPattern and falls back to the element's *Name* when there isn't one. Fakturama's SWT edits have no TextPattern, so Cust.Ref. read back as `'Cust.Ref.'` and Total as `'Total'` - four comparisons that compared a label against a value and could never pass, for any order. Visible in `probes/probe-02-fill-create-order.txt` all along (it dumps `Edit - 'Cust.Ref.'` for an editor that had just been filled) and confirmed live: `window_text()` → `'Cust.Ref.'`, `get_value()` → `'WEB-2026-0714-A17'`. Fixed with `readback.field_value()`, which reads the ValuePattern (`get_value()`, falling back to `legacy_properties()["Value"]`) and raises rather than degrading to the name if a control exposes neither. This bug masked the two below.
- **Product prices were written net into Fakturama's gross field.** `entity_resolution.product._create_product` typed `item.unit_net_price` straight into the Product editor's "Price (gross)" field; Fakturama derives net back out by dividing by (1 + VAT), so a 250.00 net chair became $210.08/unit and the order totalled 411.76 net / 78.24 VAT / 490.00 gross against an expected 570.00 / 108.30 / 678.30 (exactly the source figures ÷ 1.19). Both halves were individually correct - `_set_pricing_mode_net` really does switch the *Order* to Net, and the *Product* form really is gross - nothing converted between them. Fixed with `normalization.validators.gross_from_net` (the single home for that formula, same rule as `recompute_line_total`) applied at the one write site, plus `PRODUCT_PRICE_GROSS_LABEL_NAME` as a named constant that doubles as a price-basis check: a net-configured Fakturama would label that field "Price (net)" and `find_control` would fail closed instead of writing the wrong basis.
- **The second line's Qty. write silently landed nowhere.** `MAT-DESK-02` stayed at Fakturama's default 1.00 while line 1's 2 took, and nothing was raised - a cell is written by clicking a screen coordinate and typing, so a write that misses the cell leaves no trace at all. Arithmetic ruled out the value landing in a neighbouring cell or row; the exact mechanism was never isolated, which is the point. Two fixes, because the miss and the silence are separate failures. Locating: cells were anchored on "whichever row Fakturama is highlighting" (a guess about the app's selection state), then on a vision read of the cell boxes, which was measurably wrong twice - it put a quantity in the Item No. column and a discount in the Name column. `ui_automation/grid_geometry.py` replaces both by measuring the grid's own drawn separator lines and counting columns off them: reading a grid's *contents* is a perception problem, but reading its *geometry* is exact arithmetic, and a click at a wrong-but-plausible coordinate types into the wrong cell exactly as convincingly as into the right one. Detecting: `_fill_and_verify_line_cells` now reads the row back through `comparisons.line_row_problems` and retries from a freshly-located row before failing closed - which puts the check where `state_machine.py`'s docstring always said it belonged (immediately after entry, on the line just entered), rather than after the order is already saved.
- Two capture hazards found while doing the above, both fixed by `controls.focus_foreground` before every screenshot: a screen-region grab of an occluded window photographs whatever is on top of it (live, a grid capture came back showing this project's own editor), and a grid captured mid-relayout right after the picker closes measured 8 columns of a 10-column grid. `_measure_items_grid` re-captures on either - re-reading is safe in a way re-writing is not.

## `verification/comparisons.py::parse_ui_date` — the Invoice payment-date read-back (2026-09-06)

- The Invoice's payment-date field does not read back in the format it was written in. `orchestrator/actions.py::apply_payment` writes it as ISO (`order.payment_date.isoformat()`, e.g. `2026-07-18`), Fakturama accepts that, and then redisplays the stored value in the platform's medium date format - confirmed live reading `'Jul 18, 2026'` straight back out of a correctly-applied field. `parse_ui_date` only knew ISO and the `DD.MM.YYYY` German-locale fallback it mirrors from `normalization.normalizer`, so it returned `None`, `date_equals` failed closed, and `verify_payment_applied` routed a *correct* order to manual review. Every PAID order was affected, since this is the last state in the workflow.
- Fixed by extending `_DATE_FORMATS` with the month-name display forms (`%b %d, %Y`, `%B %d, %Y`, and the day-first `%d. %b %Y` / `%d. %B %Y`). This does not weaken CLAUDE.md's "never guess an ambiguous date" rule: a spelled-out month cannot be confused for a day, so a numeric slash date (`MM/DD` vs `DD/MM`) still fails closed exactly as before. The distinction that justifies the wider list is that this function parses text the *UI renders*, not text a human wrote - the input space is whatever the widget chooses to display, not arbitrary user input.
- Known limitation: `%b`/`%B` resolve month names through `LC_TIME`, and Python leaves that at the C locale (English) unless something calls `locale.setlocale`, which nothing here does. That matches the English-rendering VM this was confirmed on. A German-locale Fakturama would render `18. Juli 2026`, which still would not parse - it would fail closed to manual review rather than mismatch silently, but a locale-aware parse would be needed at that point.
- `verify_payment_applied` was re-run against the still-open Invoice editor from the failing run and passed with the fix in place (method `Bank Transfer`, paid checked, date `Jul 18, 2026` matching `2026-07-18`, Value `$678.30` matching the derived gross total). Noted while doing so, not fixed: nothing in `verification/` or `orchestrator/` compares currency at all, and `parse_money_text` strips currency symbols before comparing, so that `$` against a EUR order verified without complaint.

## `SAVE_AND_VERIFY_INVOICE` — the tenth state (2026-09-06)

- The workflow originally ended after applying and verifying payment, and never saved the Invoice - `orchestrator/actions.py::save_order` is Order-only. This failed invisibly: every check passed and the run reported success, but what had been verified was the contents of an open editor, not a persisted document. Confirmed live across two runs of the same image - one ended `DONE` with no `FKT_DOCUMENT` Invoice row at all and the tab still titled "New Invoice", the other persisted as `INV000001` with `PAID=TRUE`/`PAYDATE='2026-07-18'`/`PAIDVALUE=678.3` only because a human clicked Save after watching the run finish. The automation's own success signal could not tell those two runs apart, which is exactly what the fail-closed principle is meant to prevent for a question ("did the save persist?") that has a definite answer.
- Fixed with a tenth state rather than by folding a save into the payment state, mirroring `SAVE_AND_VERIFY_ORDER`: persisting a document is its own act/verify pair, and a save failure now files under its own step name in the manual review queue instead of the payment step's. `actions.save_invoice` re-activates the Invoice tab through the existing `_reactivate_editor` retry helper before clicking Save (unlike `save_order`, which can click directly because its editor is trivially active) - the toolbar's Save button acts on whichever editor is active, and by this point two editors are open. Probing for the Invoice's "Cust.Ref." is unambiguous despite the Order having the same field name, because Eclipse only exposes the active tab's contents to UI Automation.
- `verify_invoice_saved` checks the assigned invoice number, Cust.Ref., Total, and every payment field, but deliberately not the item grid: that read is a vision call, the lines were verified against the same record in the immediately preceding state, and a save does not edit lines - Total is the aggregate signal that would catch it if one changed. The payment checks are shared rather than duplicated: `payment_problems` was split out of `verify_payment_applied` so both callers run identical checks, and a post-save failure aggregates into `verify_invoice_saved`'s own reason instead of being reported under the payment step's name. See `Doc/adr/0008-save-and-verify-invoice.md`.
- Confirmed live end to end (2026-09-06): a full run from the order image reached `DONE` through the new state with the Invoice saved by the automation and verified, no manual-review entry. The tab re-activation found the Invoice's "Cust.Ref." probe without ambiguity against the Order editor's identically named field, confirming the "only the active tab's contents are exposed to UI Automation" premise `save_invoice` depends on.

## P0 refactor — what the boundaries cost and what they bought (2026-09-06)

- **The exit code was the cheapest real bug in the repo.** `__main__.main()`
  called `run_workflow(...)` and dropped the returned `WorkflowState` on the
  floor. Since `run_workflow` deliberately swallows `ManualReviewRequired`
  (it routes it to the queue and returns the state it stopped at), a run that
  failed at `normalize` and a run that reached `DONE` were indistinguishable
  from outside the process: both exit 0, both silent. Ten lines to fix, and it
  is the only defect found in this pass that a user could hit without reading
  any code.
- **Two "checks" could not fail, and one of them lied about it.**
  `VALIDATE_ORDER` re-ran `check_required_fields` and the `ADD_ORDER_LINES`
  loop re-ran `check_line_total` — both on the record `normalize_order` had
  already validated and *raised on*, so neither could ever fire. What made
  this worth fixing rather than just deleting is that `VALIDATE_ORDER`'s own
  docstring described the Task 4.1/4.3 check (addresses, products, overall
  total, before saving) that nothing in the codebase performed. The state now
  reads the Order editor's own Total Net/VAT/Total back and compares them,
  which is the first check in the whole workflow that can catch a
  *whole-order* problem — Fakturama's arithmetic over the lines, a non-zero
  order-level discount, a pricing mode that reverted to Gross. No per-line
  check can see any of those. Addresses are still not read back; the field is
  a multi-line Edit nobody has probed for read-back, and that is now said out
  loud in the function's docstring rather than implied by a state's name.
- **The selector split was costing more than duplication.** Order-editor
  knowledge lived in three files, and the two visible symptoms were both
  documented as *necessary*: ADR 0008 D5 explained why `"New Invoice"` had to
  be declared twice, and the Items grid was described in three hand-synced
  places (10 rendered columns, 6 read-back columns, and the same 6 headers
  again as literals in `comparisons.line_row_problems`). Neither was actually
  necessary - both were symptoms of partitioning selectors by *consuming
  section* rather than by *screen*. With `ui_automation/screens.py` sitting
  below every consumer, the literal is declared once and the two column
  subsets are *selected* from the rendered list by a helper that raises at
  import time on a name the grid doesn't have. The subsets came out
  byte-identical to the hand-written ones, which is the check that the vision
  prompts did not change.
- **`ui_automation` had drifted away from its own ADR, in writing.** ADR 0007
  Decision 3 says the package "is not error_handling-aware and should not
  become so"; `vision_grounding.py` and `grid_geometry.py` were raising
  `ManualReviewRequired` at 21 sites between them, with a hardcoded default
  `step` string that reached the manual-review queue as
  `"ui_automation.read_grid_rows"` instead of the workflow step. Worth
  recording as a pattern rather than an incident: the ADR was right and the
  code was wrong, and nothing detects that except reading both. The package
  now imports nothing from this project at all - a stronger property than the
  ADR asked for, and the easiest one to keep true by grep.
- **Splitting `actions.py` (815 lines) surfaced one seam worth naming.** Four
  of the five new modules are just "one screen each". `items_grid.py` is not:
  it is separated from `order_editor.py` because it is a different
  *mechanism*, not a different part of the same screen. Everything else on
  that editor is a real UIA element that can be found, written and read; the
  Items grid has no rows, no cells and no child controls, so a value gets in
  by measuring drawn separator lines, computing a coordinate, clicking it,
  typing blind, and then reading the row back through a vision call to find
  out whether any of it worked. That is the only place in the codebase that
  writes without a control to write to, and it reads better with a module
  boundary and a docstring saying so.
- **`recomputed_total` was an invariant held by call order.** It was a mutable
  field the normalizer assigned *after* constructing the line item. Every
  order-level total in the system derives from it - including the payment
  Value typed into Fakturama - so a `NormalizedLineItem` built any other way
  contributed 0.00 to an invoice, silently. Making it a computed property cost
  nothing (`validators.recompute_line_total` delegates, so Task rule 3.16
  still has exactly one home and its named importable form) and removes the
  possibility entirely. Same shape for `is_paid`: the rule deciding whether
  money is recorded as received existed as two independent copies of
  `.strip().upper() == "PAID"`, one at the site that writes payment and one at
  the site that verifies it.

## P1 refactor — the checks that were easy to state and hard to trust (2026-09-06)

- **Merging three parsers is the kind of change that looks free and isn't.**
  The separator rule (`"1.234,56"` vs `"1,234.56"`) existed in three copies,
  and they were *near*-identical, not identical: two stripped whitespace
  before parsing and one did not, because it reads dropdown text where
  `"1 9"` must not become 19. One searched for `<number>%` anywhere, which is
  right for a label like `"VAT 19 (19%)"` and wrong for a document field
  where `"abc 19%"` is a misread. So what got shared is the *primitives*, and
  each caller still composes its own cleaning explicitly. The way this was
  settled was a differential harness that reimplemented all three originals
  verbatim and compared them against the new compositions over 40 inputs -
  160 comparisons, zero differences. Worth the twenty minutes: two of the
  four differences it would have caught were ones the plan had already
  predicted in prose and would still have been easy to get wrong in code.
- **Moving constants was not enough to break the LLM dependency.**
  `validators.py` importing three field lists from `vision_extractor.py` was
  the obvious coupling, and moving them to `extraction/models.py` looked like
  the fix. It wasn't: importing `extraction.models` runs
  `extraction/__init__.py`, which imported the vision adapter, which imports
  `anthropic`. The stated property ("normalization does not depend on the LLM
  SDK") was still false, and would have stayed false and unnoticed - the
  package layout hid it. `extract_order` now imports its implementation
  modules inside the function, the same deferred-import shape the pywinauto
  boundary already uses. Confirmed by blocking `anthropic` through
  `sys.meta_path` and running the domain layer with it genuinely absent,
  rather than by reading imports.
- **A test you have not run is not a deliverable.** The new
  `grid_geometry` fixture is synthetic - a grid drawn to the structure the
  algorithm expects, since capturing a real one needs the VM. Two things it
  took to make that worth committing. First, running it: the assertions were
  written from reasoning about the algorithm, and reasoning about pixel
  lattices is exactly where an off-by-one hides. Second, a mutation check -
  perturbing each of the six tuned constants and seeing which tests notice.
  That found two real weaknesses: `_LINE_THRESHOLD` was pinned from only one
  side (a fixture drawn at 250 stays undetected whether the threshold is 235
  or 120), and the scrolled-grid test was passing for the wrong reason - it
  tripped the column-count check, whose message happens to mention scrolling
  too, and never exercised the left-edge check at all. Both fixed; five of
  six constants are now detected when perturbed.
- **The riskiest change in this pass is the smallest.** Reading a combo back
  after clicking it is four lines, and it closes the last mutation with no
  act/verify pair. But it can only be validated live: if Fakturama renders a
  selected value in a form the selecting predicate rejects, every product
  creation now fails closed on a path that previously worked. That is why the
  check reuses the *same callable* that chose the option rather than
  comparing text - it tolerates the widget re-rendering what it shows - and
  why the note to the next person is that a misfire means widening the
  comparison, not deleting the check.
- **`ResolvedEntity` earned its place by being consumed, not by being
  argued for.** ADR 0003 justified it on the grounds that "the manual-review
  log cares about" whether a record was matched or created; nothing ever read
  it. The full connection it was designed for - matching a Debtor by Customer
  ID - still needs a probe nobody has taken. What made it real was smaller:
  the run log now says "matched existing debtor 'X'" or "created product SKU
  'Y'", which is the distinction the ADR named, and `element` (the part with
  no consumer at all) is gone.

## Currency plumbing and `connect()` hardening (2026-09-12)

- **Currency is captured end-to-end, but only half the bug is fixed.**
  `RawOrder`/`NormalizedOrder` now carry `currency`, extracted with its own
  confidence field the same way `payment_method` is. The other half of the
  README-tracked bug — `comparisons.py` stripping currency symbols before
  comparing money, so a `$` total verifies clean against a EUR order — is
  deliberately not touched here. Writing a `currency_equals` comparator with
  no UI selector to feed it would be dead code, and it's not even confirmed
  Fakturama's order editor shows currency as a per-order control rather than
  a fixed installation setting. That's a VM-session question, tracked in
  `TODo.md`.
- **`FakturamaApp.connect()` was the one bare call in a module built entirely
  around polling.** Every other "is this here yet" check in `app.py` goes
  through `waits.wait_until` and raises this codebase's own
  `DialogTimeoutError`; `connect()` alone called pywinauto directly with no
  timeout and no `except`. Found while re-deriving the failure-mode picture
  for interview prep, not from a bug report: if Fakturama isn't up yet when
  the orchestrator starts, that raised a raw pywinauto exception that
  matches none of `run_workflow`'s `_UI_DISCOVERY_ERRORS`, so it crashed the
  process before a single `ManualReviewRequired` could be written to
  `out/manual_review_queue.jsonl`. The fix reuses the exact shape
  `top_level_window_by_title` already uses one function below it — polling
  `wait_until`, broad `except Exception` around the pywinauto call (the
  precise exception type isn't pinned down anywhere else in this codebase
  either, e.g. `readers.py`'s `NoPatternInterfaceError` catch), and
  `DialogTimeoutError` on timeout, which `_UI_DISCOVERY_ERRORS` already
  catches — so no `state_machine.py` change was needed to route a failed
  connect into manual review instead of a crash.

## `payment_details` — carried, not validated (2026-09-12)

- **The bug was a silent drop, not a missing check.** Extraction always read
  `RawOrder.payment_details` (it has its own confidence entry, and was
  already listed in `ORDER_LEVEL_CONFIDENCE_FIELDS`), but `NormalizedOrder`
  had no field for it and `normalize_order` never read it — so it vanished at
  the extraction→normalization boundary with nothing downstream ever the
  wiser. The fix is one field plus one line: `NormalizedOrder.payment_details`
  and `payment_details=_trim(raw_order.payment_details)` in `normalize_order`,
  same treatment as `payment_method`/`payment_status`.
- **Missing stays optional; no IBAN format check.** Both decisions are
  recorded in ADR 0011 rather than re-derived here. The short version: the
  golden sample order is `Bank Transfer` / `PAID` with `payment_details=None`,
  so "required for transfers" would fail the project's own reference order,
  and the extraction schema defines the field as free text specifically so
  non-IBAN entries (routing/account, "see invoice", etc.) aren't rejected.
- **The confidence gate needed a test, not a change.** Because
  `payment_details` was already in `ORDER_LEVEL_CONFIDENCE_FIELDS`,
  `check_confidence` already failed a present-but-low-confidence value
  closed before this fix — that was silently untested. Added a regression
  test for it alongside the carry-through and optional-absence cases.
- **Checked live on the VM (2026-09-12): there is nowhere to write it to.**
  The Debtor editor's `Miscellaneous` tab (its only other tab besides
  Addresses/Notice) has no bank/IBAN field. The Payment Method editor (the
  "Bank Transfer" record) has an `Account` combo, but it's an isolated
  control with no bank-accounts list anywhere in the app's navigation to
  back it. So `payment_details` is visible in the `--dry-run` summary and
  goes no further by design, not by gap — it's presumably the seller's own
  bank info as printed on the source document, with no Fakturama UI
  counterpart. The `TODo.md` Open item this originally added was removed;
  see ADR 0011's updated Consequences.
