
Tracks progress against `Doc/Design.md`'s six components plus the
Orchestrator. Scaffolding (module layout, docstrings, signatures) exists for
every component; Sections 1-7 all have real implementations now — what
remains is VM-probe-gated (see "Not started" below), not unimplemented code.

## Done

- **Section 1 — Image Extraction** (`extraction/`, commit `16e765b`)
  - `vision_extractor.py`: Claude Haiku 4.5 vision pass over the order image.
  - `ocr_fallback.py`: stubbed (deliberate for this demo build, per its docstring).
  - `extract_order()` in `__init__.py` wires vision + OCR-fallback together.
  - Tests: `tests/extraction/test_vision_extractor.py`, `test_ocr_fallback.py`.
- Design doc + architecture diagrams (commit `abcbe89`).
- **Section 2 — Normalization** (`normalization/`, uncommitted)
  - `normalizer.py::normalize_order` — converts `RawOrder` → `NormalizedOrder`:
    ISO-first dates (with a `DD.MM.YYYY` fallback), locale-tolerant Decimal
    money/percent parsing, trimmed text. Aggregates every parse/validation
    failure into one `ManualReviewRequired` rather than raising on the first.
  - `validators.py` — `recompute_line_total` (Task rule 3.16: `qty x
    unit_net_price x (1 - discount / 100)`, VAT excluded), `check_line_total`,
    `check_required_fields`, and `check_confidence` (now reads `RawOrder`,
    not `NormalizedOrder` — a scaffolding signature fix; confidence data
    only exists on the raw models).
  - `config.py` — env-driven thresholds, mirroring `extraction/config.py`.
  - Tests: `tests/normalization/test_normalizer.py` (golden fixture built
    from the assessment's sample order, `WEB-2026-0714-A17`),
    `test_validators.py`.
  - Rationale: `Doc/adr/0001-normalization-and-validation.md`.
- **Section 3 — UI Control Discovery** (`ui_automation/`, uncommitted)
  - `controls.py::find_control` / `find_all_controls` — bounded-retry lookup
    over a duck-typed `parent` (pywinauto's `children(control_type=, title=)`);
    raises `AmbiguousControlError` immediately on >1 match (no retry — it's
    structural, not a timing race) or `ControlNotFoundError` on timeout.
  - `waits.py` — `wait_until`, `wait_for_dialog`, `wait_for_stable_row_count`
    poll-for-state helpers, raising `DialogTimeoutError` on timeout.
  - `app.py::FakturamaApp` — generic `connect()` / `main_window()` /
    `window(title_re)`, the one module that imports `pywinauto.Application`.
  - `spikes/uia_probe.py` — implemented per its own docstring.
  - Neither `app.py` nor the spike can be imported on macOS (`from pywinauto
    import Application` fails off Windows, confirmed). `controls.py`/`waits.py`
    need no such verification: they never import `pywinauto`, so they're
    fully unit tested now.
  - **README's build-order step 1 (go/no-go UIA spike) — passed on the
    Windows 11 ARM VM (2026-09-04):** `python spikes/uia_probe.py` against a
    running Fakturama window returned a rich, fully named control tree
    (toolbars, buttons like `'Create: New Order'`/`'Create: New Invoice'`,
    edits, search boxes) on the first try — no Java Access Bridge fallback
    needed. Raw dump: `Archieve/uia-output.txt`.
  - `spikes/uia_probe_editor.py` added: same read-only connect, but takes a
    keyword arg and prints only the matching descendant subtrees (falling
    back to the full tree if nothing matches), so the Order/Invoice editors
    and each entity search dialog can be probed individually instead of
    reading the whole main-window dump every time.
  - Tests: `tests/ui_automation/test_waits.py`.
  - Rationale: `Doc/adr/0002-ui-automation-testability-boundary.md`.
- **Section 4 — Entity Resolution** (`entity_resolution/`, uncommitted)
  - `resolver.py::resolve_exact_or_create` — shared zero/one/many
    search-then-create decision, now raising `ManualReviewRequired` (with
    `entity`/`step` context) on ambiguity. `resolver.py::search_grid_exact` —
    new shared "search" half: type a key into a search box, then read
    Fakturama's custom-rendered results grid via vision grounding (see
    below), since those grids expose no rows to UIA at all (confirmed by
    probing every entity's list view — `probes/probe-06-debitors.txt`,
    `probe-07-products.txt`, `probe-09-Payment.txt`).
  - `ui_automation/vision_grounding.py` (new) — `capture_control_image` +
    `read_grid_rows`, the vision-grounded fallback for reading
    UIA-invisible grids (Doc/Design.md's own sanctioned fallback for
    custom-rendered elements). Reused by Section 5/orchestrator later.
  - `ui_automation/controls.py` — `find_control`/`find_all_controls` gained
    an optional `auto_id` filter (many Fakturama controls have no
    accessible name and are only addressable this way).
  - `matching.py` (new) — pure `exact_text_matches`/`exact_vat_matches` row
    filters (no UI, no network).
  - `models.py` (new) — `ResolvedEntity` (identity, `created`, `element`)
    return type, replacing the scaffold's bare `Any`.
  - `config.py` (new) — env-driven timeouts plus every verified
    `auto_id`/button title from the VM probe (`probes/probe-*.txt`).
  - `debtor.py`, `product.py`, `vat_rate.py`, `payment_method.py` — all
    fully implemented and unit-tested (search, exact match,
    create-and-fill-form, save) against verified control identifiers.
    `product.py`'s `create()` resolves a missing VAT rate first, per the
    original scaffold's "not skipped" instruction. VAT and Payment each
    needed a second probe pass (`probes/probe-08-vats.txt`,
    `probe-0801-vats.txt`, `probe-10-payment-create-form.txt`) after an
    initial pass captured a stale editor instead of the target
    list/create form; Fakturama's own create forms call these entities
    "TAX Rate" and "New Term of Payment" internally.
  - Tests: `tests/entity_resolution/test_resolver.py` (the pure
    `resolve_exact_or_create` half only), `test_matching.py`.
  - The two `ComboBox.select(...)` calls (`debtor.py` Country, `product.py`
    VAT) are resolved: probing the combos directly (with each dropdown
    actually open) found the popup renders as a single, childless `Pane`
    that isn't even a descendant of the main window - so, unlike the list
    grids, there was no control to read `.texts()` on regardless of
    UIA-opacity. `entity_resolution/combos.py` (new) instead screenshots
    `main_window` itself right after opening the combo (a screen-rect
    grab captures the dropdown overlay too, without needing a handle to
    the popup), asks `ui_automation.vision_grounding.read_combo_options`
    (new) to name **and locate** each option, and clicks the matched
    option's absolute screen coordinate - the first coordinate-based
    click in this codebase, alongside the existing UIA-selector approach.
    `pick_option` mirrors `matching`'s fail-closed 0/1/many exact-match
    shape; `product.py`/`debtor.py`'s guessed `.select()` calls are gone.
  - Rationale: `Doc/adr/0003-entity-resolution.md`,
    `Doc/adr/0006-combo-selection.md`. Plan:
    `.claude/plans/entity-resolution.md`,
    `.claude/plans/entity-resolution-residual.md`.
- **Section 5 — Verification** (`verification/`, uncommitted)
  - `order_verification.py::verify_order_saved` — confirms the Order's own
    tab/pane title no longer reads `"New Order"` (an assigned order number
    was persisted), then reads back Cust.Ref./Total Gross/Discount-derived
    Total Net/VAT/Total and the item-row grid (vision-grounded) against the
    `NormalizedOrder`. Signature gained a `normalized_order` parameter
    beyond the original scaffold so persistence and field-matching are
    checked together.
  - `invoice_verification.py::verify_invoice_matches_order` — re-verifies
    the linked Invoice's Cust.Ref., Total, and item lines against the same
    normalized record (Task 5.1), independent of Fakturama's own
    Invoice-generation step.
  - `payment_verification.py::verify_payment_applied` — confirms payment
    method, and (if PAID) the paid toggle/payment date/full invoice Value,
    or (if not PAID) that none of those were invented (Task 5.2/5.3/5.6).
  - `comparisons.py` (new) — pure `money_equals`/`percent_equals`/
    `date_equals`/`text_equals`/`order_level_totals`/`line_row_problems`,
    bridging normalization's typed `Decimal`/`date` values against the
    plain strings read back from the UI.
  - `readback.py` (new) — shared `window_title`/`read_field_text`/
    `read_toggle_state`/`read_grid` primitives every verification function
    composes; `read_grid` reuses `ui_automation.vision_grounding` for the
    Order/Invoice editor's own item-row grid, confirmed UIA-invisible the
    same way entity resolution's list grids are.
  - `config.py` (new) — env-driven timeouts; Order/Invoice editor fields
    are selected **by accessible name**, not `auto_id` (unlike Section 4's
    entities) — comparing `probes/probe-01-create-order.txt` against
    `probe-02-fill-create-order.txt` found every field `auto_id` in that
    editor differs between app sessions while names stay stable. All three
    controls needed for Data > Documents, the linked Invoice editor's
    layout, and the Invoice's payment controls (paid checkbox/payment
    date/Value) have **no VM probe yet** and are left as explicit
    empty-string placeholders (`# TODO probe`) that fail closed rather than
    guessed identifiers — see `Doc/adr/0004-verification.md`.
  - All three functions return `True` or raise one aggregated
    `ManualReviewRequired` collecting every mismatch found, mirroring
    `normalization.normalizer.normalize_order`'s fail-closed shape, rather
    than a bare `False`/first-problem-only raise.
  - Tests: `tests/verification/test_comparisons.py` — pure, no fakes,
    using the golden `WEB-2026-0714-A17` sample order as the known-good
    fixture.
  - Rationale: `Doc/adr/0004-verification.md`. Plan:
    `.claude/plans/verification-module.md`.
- **Section 6 — Error Handling** (`error_handling/`, uncommitted)
  - `manual_review.py::route_to_manual_review` — appends one JSON object
    per line to a single queue file (`out/manual_review_queue.jsonl` by
    default, per the README's shared folder layout), holding a timestamp,
    the source image path, and the failing `step`/`reason`. Fail-safe by
    contract: any write failure is caught and reported to stderr instead
    of propagating, since this is the terminal handler for a workflow
    run. `out_dir` and `now` are injectable keyword args (mirroring
    Sections 1/5's `client=`/`normalized_order=` seam) so tests never
    touch the real `out` folder or wall-clock time.
  - `config.py` (new) — env-driven `OUT_DIR`/`QUEUE_FILENAME`, mirroring
    every other section's `config.py`.
  - `exceptions.py::ManualReviewRequired` left unextended (still just
    `step`/`reason`); `route_to_manual_review` forwards a `details`
    attribute via `getattr` if a future caller sets one, so richer partial
    state can be added later without changing this function again — see
    Future work below and `Doc/adr/0005-error-handling.md`.
  - Tests: `tests/error_handling/test_manual_review.py` — JSONL
    write/append, `out_dir` auto-creation, the fail-safe path (unwritable
    `out_dir` still returns `None`), and the `details` forwarding hook.
  - Rationale: `Doc/adr/0005-error-handling.md`. Plan:
    `.claude/plans/error-handling.md`.
- **Section 7 — Orchestrator** (`orchestrator/`, uncommitted)
  - `state_machine.py::run_workflow(image_path, *, app=None, client=None,
    out_dir=None, settle_seconds=...)` — the 9-state loop (EXTRACT →
    NORMALIZE → OPEN_ORDER → POPULATE_ORDER_FIELDS → ADD_ORDER_LINES →
    VALIDATE_ORDER → SAVE_AND_VERIFY_ORDER → CREATE_AND_VERIFY_INVOICE →
    APPLY_AND_VERIFY_PAYMENT), threading one `FakturamaApp`-like handle and
    one vision `client` through every section. One `try/except` around the
    whole sequence catches both `ManualReviewRequired` (from any section)
    and a bare `ui_automation` control-discovery failure
    (`ControlNotFoundError`/`AmbiguousControlError`/`DialogTimeoutError`,
    converted to `ManualReviewRequired(state.value, ...)`), routing to
    `error_handling.manual_review.route_to_manual_review`. Returns the
    `WorkflowState` last reached (`DONE` on success) rather than `None`.
  - `actions.py` (new) — every UI write action
    (`open_new_order`/`populate_order_fields`/`add_order_line`/
    `save_order`/`create_linked_invoice`/`apply_payment`), kept out of
    `state_machine.py` so the loop reads as control flow. The main
    toolbar's `"Create: New Order"` button and the New Order editor's own
    Pane (reusing `verification.config.ORDER_TAB_TITLE_UNSAVED`) are
    probed and pinned; the order-line grid's entry affordance and the
    Data > Documents "create linked invoice" action have no VM probe yet
    and are left as explicit empty-string `# TODO probe` placeholders in
    `config.py`, so they fail closed against a real window (see "Not
    started" below).
  - **Debtor-to-Order attachment (2026-09-06, live-VM probe session)** —
    `populate_order_fields`'s customer-field placeholder
    (`ORDER_CUSTOMER_FIELD_AUTO_ID`) was a wrong assumption (a plain Edit
    to `set_text()`), not an un-probed one: the customer field is a
    multi-line address Edit you attach a Debtor to via a "Select the
    address" picker, opened by clicking a small blank-named Image
    structurally located next to the "Addresses" label
    (`config.ORDER_ADDRESSES_LABEL_NAME`). That picker is a genuinely
    separate top-level OS window, not found reliably by pywinauto's own
    window enumeration - `ui_automation.app.FakturamaApp.top_level_window_by_title`
    (new) uses raw `win32gui.EnumWindows` instead, confirmed live this is
    the only mechanism that reliably finds it. Its UIA-invisible grid is
    searched and read via a new `ui_automation.vision_grounding.read_grid_rows_located`
    (rows + bounding boxes, mirroring `read_combo_options`), matched by
    "exactly one row after searching by company name" rather than exact
    cell-text equality (that column can render too narrow to show the
    full company name - see `Doc/adr/0007-orchestrator.md`'s Decision 7
    and Future work below for the more correct fix). `ORDER_PAYMENT_METHOD_FIELD_AUTO_ID`
    is deleted, not filled in - confirmed live there is no Payment Method
    field on the Order screen at all; it's attached later at the Invoice
    stage by `apply_payment`, unchanged. Also fixed, found during live
    verification: `entity_resolution.debtor`'s Company field needed a new
    `ui_automation.controls.type_text` (real keystrokes) instead of
    `set_text()`, which silently failed to persist it through Save.
    Verified live end-to-end: `populate_order_fields` now completes and
    the workflow advances to `ADD_ORDER_LINES`.
  - `config.py` (new) — env-driven timeouts plus the selectors above;
    reuses `entity_resolution.config`/`verification.config` constants
    rather than duplicating them.
  - `__main__.py` (new) — `python -m fakturama_automation.orchestrator
    <image_path>` CLI wrapper around `run_workflow`.
  - `ui_automation.app.FakturamaApp` is imported inside `run_workflow`'s
    body (not at module level) so the orchestrator package stays
    importable cross-platform when a caller/test supplies its own fake
    `app` — see `Doc/adr/0007-orchestrator.md`.
  - No unit test (UI-writing state machine) — verify live on the VM;
    doesn't exercise a full extract-to-`DONE` run either way (see ADR's
    Consequences).
  - Rationale: `Doc/adr/0007-orchestrator.md`. Plan:
    `.claude/plans/orchestrator.md`.

## Next

All six components and the orchestrator now have real implementations.
What remains is VM-probe-gated (see "Not started" below), not a new
section.

- **VM verification needed**: `add_order_line`'s Qty./Discount fill step
  (`orchestrator/actions.py`) reads both columns from a single screenshot
  of the Items grid (`vision_grounding.read_active_row_cells`), assuming
  both fit in the visible viewport at once. On the dev machine used for
  the 2026-09-06 VAT-duplicate debugging session (see "Not started"
  below), the grid has too many columns (Pos./Qty./Item No./Picture/Name/
  Description/VAT/U.Price/Discount/Price) to show Qty. and Discount
  together — confirmed live: at every horizontal scroll position tried,
  one or the other column always fell outside the captured control's
  bounds. Fails closed (`ManualReviewRequired`) rather than misreading, so
  not unsafe, but blocks completing an order on a narrow-enough window.
  Also observed: the grid pane's own reported UIA rect extended past the
  main window's rect on that machine — possibly a DPI-scaling quirk local
  to that dev box rather than a real constraint on the target Windows 11
  ARM VM. Needs checking against the actual VM before deciding whether
  `add_order_line` needs a scroll-and-re-read fix (read Qty. at the
  default scroll position, scroll right, read Discount separately) or
  this was dev-machine-only. Update: a later clean run in this same
  session (fresh Fakturama process, both line items added end-to-end, see
  "Not started" below) did *not* hit this - Qty. and Discount were both
  visible together that time. Not reproduced a second time, so leaning
  towards this having been a transient scroll-position artifact of the
  earlier debugging session rather than a fixed viewport constraint - but
  still unverified on the real VM, so leaving this open.

## Not started / not yet stubbed

- Data > Documents, the linked Invoice editor, and the Invoice's payment
  controls (paid checkbox, payment date, Value) have **no VM probe at
  all** — `verification/config.py` leaves their selectors as explicit
  empty-string placeholders (see Section 5's Done entry and
  `Doc/adr/0004-verification.md`). The Order editor's own fields (Cust.
  Ref./Total Gross/Discount/VAT/Total, and its tab-title-as-order-number
  signal) are done — probing found their `auto_id`s are session-unstable
  but their accessible names are not, so Section 5 selects them by name.
  Use `spikes/uia_probe_editor.py <keyword>` (or a full
  `spikes/uia_probe.py` dump — see `.claude/plans/entity-resolution.md`'s
  Gate section for why a full dump beats a keyword-filtered one for
  blank-named controls) against a live saved Order, Data > Documents, and
  a linked Invoice (including its payment area) to fill these in.
- Verifying via Data > Documents itself (Task 4.5/5.5's own prescribed
  check — a second, independent read distinct from reading the editor's
  internal fields) — not implemented; would need its own vision-grounded
  grid read once the pane above is probed. See
  `Doc/adr/0004-verification.md`'s Consequences.
- The Order editor's own line grid is not exposed to UIA either
  (`probes/probe-01/02-*.txt`) — order-line entry will need the same
  vision-grounding/keyboard approach as entity search, not a plain
  `find_control` selector. `orchestrator/config.py` leaves
  `ORDER_LINE_ADD_BUTTON_TITLE`/`INVOICE_FROM_ORDER_BUTTON_TITLE`/
  `INVOICE_EDITOR_PANE_NAME` as explicit empty-string placeholders for
  this reason (Section 7's Done entry, `Doc/adr/0007-orchestrator.md`).
  The customer/payment-method attachment gap this bullet used to list is
  done — see Section 7's Done entry above.
- A live run (2026-09-06) reached `ADD_ORDER_LINES` and failed inside
  `entity_resolution.product.resolve_product`'s VAT-rate creation with
  `no Edit control named None (auto_id='133868') found` -
  `VAT_FORM_NAME_AUTO_ID` in `entity_resolution/config.py` is a hardcoded
  auto_id from an earlier probe session, and per this codebase's own
  documented finding (`CLAUDE.md`, `Doc/adr/0003`), auto_ids are not
  stable across Fakturama restarts. This is a pre-existing gap in Section
  4's VAT-rate form filling, unrelated to the order-line-entry gap above
  - `vat_rate.py`'s create form needs the same structural (name-based, not
  auto_id-based) locator treatment `debtor.py`'s blank-named fields
  already got, not a fresh hardcoded auto_id.
- A separate `ADD_ORDER_LINES` run (2026-09-06) failed with `no Text
  control named 'Search:' (auto_id=None) found within 5.0s`, right after
  `app.top_level_window_by_title` had already reported the "Select a
  product" dialog present - meaning the wrong window was found, not that
  none appeared. Root cause: `top_level_window_by_title` matched by title
  via raw `win32gui.EnumWindows` and silently took the *first* visible
  window with that exact title, with no check for a second one - unlike
  every other control lookup in this codebase
  (`ui_automation.controls.find_control`), which fails closed
  (`AmbiguousControlError`) as soon as it sees more than one match rather
  than picking arbitrarily. A stale/leftover "Select a product" window
  (e.g. one left open from manually clicking around the app outside the
  automated flow) sitting alongside the freshly-opened one could get
  grabbed instead, handing back a window that may not have its own
  "Search:" box rendered (or any child controls at all) yet. Fixed:
  `top_level_window_by_title` now collects every matching visible window
  and raises `AmbiguousControlError` if more than one exists, mirroring
  `find_control`'s convention, instead of guessing. Not itself unit-tested
  - `ui_automation/app.py` is the one module that imports `pywinauto`
  directly and can't be exercised off the VM (`CLAUDE.md`'s platform
  note) - verify live by re-running `ADD_ORDER_LINES` with no other
  "Select a product"/"Select the address" window left open beforehand.
  That fix didn't resolve a repeat live run (2026-09-06) with the exact
  same `no Text control named 'Search:' ... found within 5.0s` error - no
  `AmbiguousControlError` was raised, ruling out a stale duplicate window.
  Live observation (reported by the user watching the VM) isolated the
  actual cause instead: the "Select a product" picker can visibly flash
  open and close again within a fraction of a second of the toolbar click
  that opens it (root cause not fully isolated - most likely an input
  race between that click and the dialog's own initial render/focus).
  `top_level_window_by_title` only needs to observe a window once to
  succeed, so it handed back a reference to a dialog that was already
  gone by the time the code got around to reading its "Search:" box -
  same symptom, different cause than the first fix addressed. Fixed:
  `ui_automation.app.FakturamaApp` gained `top_level_window_is_open`
  (single no-polling snapshot, factored out of the same
  `_visible_window_handles` helper `top_level_window_by_title`/
  `wait_until_top_level_window_closed` now share); `orchestrator.actions`
  gained `_open_picker_dialog` (click, then re-check
  `top_level_window_is_open` after `config.DIALOG_STABILIZE_SECONDS`,
  re-clicking up to `config.DIALOG_OPEN_ATTEMPTS` times if the dialog
  already vanished), used by both `add_order_line`'s "Select a product"
  picker and `_attach_debtor_to_order`'s "Select the address" picker
  (structurally identical, so given the same fix even though only the
  former has been observed to flash-close live). Also not unit-tested for
  the same cross-platform reason as the first fix - verify live.
- Re-running to verify the above surfaced a different, earlier live
  failure (2026-09-06) before ever reaching `ADD_ORDER_LINES`: `resolve_
  debtor` raised `ManualReviewRequired` with `no unique option matching
  'Germany'; options were ['all', 'andy']` - the Country combo's vision
  read (`entity_resolution.combos._read_open_combo_options`) came back
  with nonsense options. Root cause: unlike every other UI-changing-then-
  read step in this codebase (`resolver.search_grid_exact` sleeps after
  typing into a search box; `add_order_line` sleeps after `set_text` into
  a picker's search Edit), this function had no settle delay at all
  between opening/type-ahead-scrolling the combo and screenshotting it for
  the vision read - capturing it mid-open/mid-scroll is a much likelier
  explanation for meaningless option text than the vision model
  hallucinating real country names into nonsense. Fixed: `select_vat_
  option`/`select_exact_option`/`_read_open_combo_options` gained a
  `settle_seconds` keyword (default `entity_resolution.config.
  SEARCH_SETTLE_SECONDS`, same constant `resolver.search_grid_exact`
  already uses), slept once right before the screenshot. Tests updated
  (`tests/entity_resolution/test_combos.py` now passes `settle_seconds=0`
  throughout, matching every other settle-based test in this codebase).
  Confirmed fixed by a live re-run (2026-09-06): the debtor already
  existed (created by an earlier attempt), so this run skipped straight
  past the Country combo into `_attach_debtor_to_order`'s own "Select the
  address" picker - temporary diagnostic logging on that picker-open
  step showed it observed, then stayed open with its "Search:" box
  present continuously for ~3.8s (no flash-close at all this time),
  confirming the `_open_picker_dialog` retry/stabilize fix above is sound
  and not itself the problem. This run instead hit a new, unrelated wall:
  `populate_order_fields` raised `2 rows in the "Select the address"
  dialog after searching for 'Northstar Office GmbH' (expected exactly
  one); found: Northstar Office GmbH, Northstar Office GmbH` - a genuine
  duplicate Debtor record in Fakturama's own database (almost certainly
  created by an earlier attempt during this same debugging session),
  correctly fail-closed rather than guessing which row to attach
  (`CLAUDE.md`'s central rule) - not a code bug. Blocked on manual
  cleanup: delete or rename one of the two "Northstar Office GmbH"
  Debtor records in Fakturama before the next run, then retry -
  `ADD_ORDER_LINES` itself (and its own picker-flash-close fix) still
  hasn't been exercised by a clean run yet.
  A later clean run (2026-09-06) finally reached a second `add_order_line`
  call and reproduced the identical `no Text control named 'Search:'
  (auto_id=None) found within 5.0s` error there - but only on the *second*
  line item, not the first. Root cause: `_open_picker_dialog`'s stabilize
  check only confirms the dialog's OS-level top-level window is visible
  (`app.top_level_window_is_open`), not that its content (the "Search:"
  label/Edit/grid) has actually rendered. On a first-ever open this gap
  didn't matter - content reliably appeared well within
  `_pick_single_row_in_dialog`'s own follow-on 5s `find_control` poll. On
  a *reopen* of the same dialog title, the same flash-open-close race this
  bullet already documents can recur after the stabilize check has
  already passed (window visible at `stabilize_seconds`, then torn down
  again before the follow-on 5s content poll completes) - landing past
  the point `_open_picker_dialog` considered "safe", so none of its retry
  logic covered it. Fixed: `_open_picker_dialog` now also probes for the
  dialog's own "Search:" Text control (a short `stabilize_seconds`
  timeout, not the caller's full `timeout_seconds`) once the window looks
  stable, and retries (re-clicking `open_button`) the same way it already
  did for a vanished window if that probe fails too - shared by both
  pickers, same as the round above. Not itself unit-tested for the same
  cross-platform reason as the fixes above.

  A live re-run confirmed the content-probe fix alone was **not**
  sufficient: `_open_picker_dialog`'s probe reliably confirmed "Search:"
  present, yet the very next step - `_pick_single_row_in_dialog`'s own
  first `find_control` call on the same dialog, moments later - still
  timed out, meaning the dialog can vanish *after* content is confirmed
  present too, not only before. Fixed further: `_pick_row_via_picker`
  (new, `actions.py`) wraps the *entire* open-search-pick cycle
  (`_open_picker_dialog` with `attempts=1` + `_pick_single_row_in_dialog`)
  as one retryable unit - a `ControlNotFoundError`/`DialogTimeoutError`
  from either step retries the whole cycle from a fresh click, closing any
  stray leftover dialog (Escape) first so the retry's own
  `top_level_window_by_title` can't collide with it. `add_order_line`/
  `_attach_debtor_to_order` now call this instead of the two separate
  calls.

  Live testing this fix (2026-09-06) surfaced something more concerning
  than a simple retry gap: calling the real `add_order_line` repeatedly
  against the same already-open Order tab (same SKU, already-resolved
  Product, no new-entity creation) was **not** consistently flaky - it
  ranged from succeeding instantly to failing all 3 retry attempts in a
  row, with no code-observable pattern distinguishing the two (ruled out
  by direct live experiment: OS focus being stolen to another window
  during the dialog's lifetime; calling `dialog.set_focus()`; querying the
  dialog's UIA tree repeatedly/rapidly; too-short a gap between retries -
  a 3s cool-down between attempts made no difference, still 3/3 failures).
  The failure rate appeared to *worsen* over the course of an extended
  live debugging session (many dozens of scripted open/close cycles
  against one running Fakturama process) - consistent with the live
  Fakturama process itself degrading (a resource/handle leak or similar)
  rather than a discoverable logic bug in this codebase. Not resolved:
  the widened retry above is a genuine improvement for ordinary transient
  flakiness and is kept, but cannot be verified to fully fix
  `ADD_ORDER_LINES` until re-tested against a freshly-restarted Fakturama
  process. Next step: restart Fakturama, re-run `ADD_ORDER_LINES` on an
  order with at least two line items, and if it still fails at a similar
  rate on a fresh process, this points at something outside this
  codebase's control (Fakturama/SWT/UIA-bridge stability) rather than a
  fixable client-side race.

  A later session (2026-09-06, continued) tracked down the actual root
  cause of the user-reported symptom ("adds the first item 3 times, then
  errors") with a live Fakturama instance connected directly: two
  separate, real bugs, not the suspected "process degradation".

  First: `entity_resolution.vat_rate._create_vat_rate` filled the "Value"
  field with plain `controls.type_text` (click + type, no clear). That
  field defaults to pre-filled "0%", so the keystrokes inserted into the
  existing text instead of replacing it - confirmed live (screenshot of
  the saved record) that Fakturama silently kept Value at "0%" regardless
  of what was typed, while Name saved correctly as e.g. "19%". Since
  `resolve_vat_rate`'s search matches by that same Value column, it could
  never find its own previously-created rate on the next lookup, creating
  a fresh duplicate "19%"/Value-0% record every time a new product needed
  that VAT percent - almost certainly how the product catalog accumulated
  enough duplicate/junk data over repeated dev/test runs to eventually
  destabilize the "Select a product" picker (see the `AmbiguousControlError`
  history above this run's `resolve_vat_rate` even had to route around).
  Fixed: clear the field (`Ctrl+A`+`Delete`) before typing and commit with
  a trailing `Tab`, mirroring `_fill_grid_text_cell`'s existing pattern.
  Confirmed live: Value now reads back correctly (e.g. "25%") both before
  and after Save.

  Second, and the direct cause of the duplicate-add symptom itself: typing
  an exact SKU into the "Select a product" dialog's search box can make
  Fakturama auto-confirm the single narrowed-down match and close the
  dialog **on its own** - before `_pick_single_row_in_dialog` ever gets to
  read the grid, click the row, or click OK. Traced live with
  instrumentation on every internal step (`_open_picker_dialog`/
  `_pick_single_row_in_dialog` wrapped to print success/failure): all 3
  retry attempts reported the identical "no Text control named 'Search:'
  ... found within 5.0s" failure (the re-find right after typing, `actions.py`
  ~line 403) with `[pick] SUCCESS` never printed once - yet the Items grid
  showed 3 duplicate rows of that same SKU afterward. The dialog closing
  itself post-type is a *success* (the row is already added), not the
  flash-close race the earlier fixes in this log addressed - but the old
  code had no way to tell the difference, so the retry loop reopened the
  picker and re-added the row on every attempt that hit this. Fixed:
  `_pick_single_row_in_dialog` now checks `dialog.exists()` right after
  typing (before re-finding "Search:"), via a new `_dialog_still_exists`
  helper that also treats a raw `_ctypes.COMError` from a stale
  handle-based wrapper's `.exists()` re-resolution as "gone" (confirmed
  live this can happen) rather than propagating it - if the dialog is
  already gone, returns immediately instead of continuing to look for its
  (now nonexistent) content. Confirmed live, end-to-end, on a freshly
  restarted Fakturama process with both fixes in place: a 2-line-item
  order added both lines exactly once each with correct Qty./quantities/
  VAT/totals (`CHR-ERG-01` x2 @ $250 + `MAT-DESK-02` x3 @ $40 = $620.00
  gross), no manual-review entry, no duplicate rows, no duplicate VAT
  records.

## Future work

- `add_order_line` originally inserted a blank row (the Items toolbar's
  second Image, "add a blank row") and typed every cell by hand -
  superseded (2026-09-06) by the first Image's "Select a product" picker
  instead (structurally identical to `_attach_debtor_to_order`'s "Select
  the address"), which fills Item No./Name/Description/Price/VAT
  straight from the Product's own catalog record. This was a genuine
  design fix, not just a workaround: the blank-row approach hit three
  separate live bugs in one run - Name opens its own unprobed popup
  editor rather than editing inline; the VAT cell's dropdown-selection
  didn't reliably take effect (line 1's VAT silently stayed "Tax-free"
  even though a correct "19%" rate existed and no error was raised); and
  vision-computed cell positions for two different columns (Item No. and
  Discount) were confused with each other on a second line. Only Qty./
  Discount are still filled cell-by-cell now (the catalog record has no
  per-order quantity/discount), so the surface area for that class of bug
  is much smaller, but not zero - if a future run shows either of those
  two values landing in the wrong cell, the same vision-misidentification
  risk is the first thing to check.
- Match by the Debtor's own unique No./Customer ID, not by company name,
  in `orchestrator/actions.py::_attach_debtor_to_order`'s "Select the
  address" picker. Confirmed live (2026-09-06): that dialog's Company
  column can render too narrow to show the full value (a real "Northstar
  Office GmbH" row read back visibly clipped to "thstar Office ..."), so
  an exact-text-match check against the untruncated target can never pass
  even when the row is correct - every other resolver in this codebase
  verifies its own search results independently
  (`entity_resolution.matching.exact_text_matches`), but this dialog can't
  do that the same way. The current fix instead trusts Fakturama's own
  Search filtering and requires exactly one row after searching by
  company name - a narrower guarantee, since it relies on Fakturama's
  search semantics rather than independently confirming them. Matching by
  No./Customer ID instead (short, never clipped, visible in this same
  grid) would restore independent exact-match verification, but needs
  `entity_resolution.debtor.resolve_debtor` (`ResolvedEntity`) to capture
  and expose that identifier first - not done because it touches
  `entity_resolution/models.py`/`debtor.py` beyond this task's scope.
- Localization, and accepts different formats to numbers, dates, currencies,..., etc.
- Country-code→name mapping for `debtor.py`'s Country combo: if
  Fakturama's real Country options turn out to be full names ("Germany")
  while normalized data holds an ISO code ("DE"), `combos.select_exact_option`
  correctly fails closed to manual review rather than guessing — see
  `Doc/adr/0006-combo-selection.md`, Consequences.
- VM verification for `entity_resolution/combos.py`'s two coordinate-click
  assumptions (not blocking — both fail closed if wrong, they just haven't
  been tried against a live window yet): the captured screenshot's pixels
  map 1:1 to screen coordinates (no DPI scaling), and a combo's dropdown
  renders within `main_window`'s bounding rectangle rather than
  overflowing it — see `.claude/plans/entity-resolution-residual.md`'s
  "Known limitations".
- Rich partial-state capture for manual review (deferred from Section 6,
  `Doc/adr/0005-error-handling.md`): extend `ManualReviewRequired` with an
  optional payload (e.g. `details`), thread it through the ~10 existing
  raise sites across extraction/normalization/entity_resolution/
  verification, and add a `Decimal`/`date`-aware JSON encoder so a queue
  entry can carry the actual `NormalizedOrder`/ambiguous candidates, not
  just `step`/`reason`. `manual_review.route_to_manual_review` already
  forwards a `details` attribute via `getattr` if set, so this is additive
  and needs no further change to that function.
- Per-entry manual-review files (one JSON file per stuck order, e.g. under
  `out/manual_review/`) plus a separate human-readable log, if the single
  `out/manual_review_queue.jsonl` append-only file proves insufficient
  once a human/tool actually processes entries (no claim/delete workflow
  today) — see `Doc/adr/0005-error-handling.md`'s Consequences.
