# Status and open work

Per-section status for the six components of [Doc/Design.md](Doc/Design.md)
plus the Orchestrator. This file tracks **what is real vs. still open** —
nothing else:

- *Why* the live app needed what it needed → [Doc/implementation-notes.md](Doc/implementation-notes.md)
- Decisions the design doc didn't dictate → [Doc/adr/](Doc/adr/)
- The ranked list of task-spec gaps and what I'd do with three more hours →
  [README.md](README.md#next-steps) (single source of truth; not duplicated here)

**Current state:** all seven sections implemented and committed, then
refactored (P0 pass, ADR 0009). The last full live run to `DONE` was
**2026-09-06** (`INV000001`), which predates the refactor. The first
post-refactor live run (2026-09-15) did **not** reach `DONE` — it stopped in
`resolve_product`, and the two regressions it found are Open items 1 and 2.

## Done

| # | Section | Package | Files | ADR |
|---|---|---|---|---|
| 1 | Image Extraction | `extraction/` | `vision_extractor.py` (Claude Haiku 4.5 vision pass), `ocr_fallback.py` (deliberate no-op stub), `models.py`, `config.py`, `__init__.py::extract_order` | — |
| 2 | Normalization & Validation | `normalization/` | `normalizer.py`, `validators.py`, `models.py`, `config.py`; `payment_details` carried through (was silently dropped) | 0001, 0011 |
| 3 | UI Control Discovery | `ui_automation/` | `controls.py`, `waits.py`, `app.py`, `exceptions.py`, `config.py`; `vision_grounding.py` + `grid_geometry.py` added later (see 4 and 7); `spikes/uia_probe.py`, `spikes/uia_probe_editor.py`, `probes/*.txt` | 0002 |
| 4 | Entity Resolution | `entity_resolution/` | `resolver.py`, `debtor.py`, `product.py`, `vat_rate.py`, `payment_method.py`, `matching.py`, `combos.py`, `models.py`, `config.py` | 0003, 0006 |
| 5 | Verification | `verification/` | `order_verification.py`, `invoice_verification.py`, `payment_verification.py`, `comparisons.py`, `readback.py`, `config.py` | 0004 |
| 6 | Error Handling | `error_handling/` | `manual_review.py`, `exceptions.py`, `config.py` | 0005 |
| 7 | Orchestrator | `orchestrator/` | `state_machine.py`, `actions.py`, `config.py`, `__main__.py` | 0007 |
| 7b | `SAVE_AND_VERIFY_INVOICE` (tenth state) | `orchestrator/`, `verification/` | `state_machine.py`, `actions.py::save_invoice`, `invoice_verification.py::verify_invoice_saved`, `payment_verification.py::payment_problems` | 0008 |
| 9 | P1 refactor: one parser, real LLM boundary, verified creation | all | new `normalization/parsing.py`, `ui_automation/readers.py`, `tests/ui_automation/test_grid_geometry.py`; deleted `verification/{readback,config}.py` and `matching.parse_vat_text`; `entity_resolution/*` read every created record back; `combos.py` verifies the click; `state_machine.py` + `__main__.py` gain logging and `--dry-run` | 0010 (amends 0003, 0004) |
| 8 | P0 refactor: dependency direction, one selector home, honest states | all | new `ui_automation/screens.py` + `locators.py`; `actions.py` → `orchestrator/steps/{order_editor,invoice_editor,items_grid,pickers,toolbar}.py`; `__main__.py` (exit code), `state_machine.py`, `normalization/models.py` (computed `recomputed_total`, `is_paid`), `ui_automation/{exceptions,vision_grounding,grid_geometry,controls}.py`, all three `config.py` trimmed to tunables | 0009 (amends 0004, 0007, 0008) |
| 10 | Combo popup crop + settle timing | `entity_resolution/` | `combos.py` (locate and screenshot the popup directly instead of the whole `main_window`; capture-origin threaded into the click math), `config.py` (`COMBO_POPUP_SETTLE_TIMEOUT_SECONDS`); `spikes/uia_probe_combo_region.py`, `probes/probe-13-combo-region-settle-{country,vat}.txt` | 0013 (amends 0006) |
| 11 | Debtor matching by Customer ID (task 2.3) | `entity_resolution/`, `ui_automation/` | `debtor.py` (five-field match, real identity read-back), `matching.py` (`exact_debtor_matches`), `screens.py` (`DEBTORS_SEARCH_COLUMNS` corrected, `DEBTOR_CUSTOMER_ID_EDIT_NAME`); `tests/entity_resolution/test_matching.py` | 0014 |

Notes worth keeping in one place:

- **Selectors:** every Fakturama control identifier lives in
  `ui_automation/screens.py`, by screen, and nothing else declares one. Each
  package's `config.py` holds only timeouts/retry counts.
- **Dependency rule:** `ui_automation` imports nothing from this project;
  `verification` and `entity_resolution` are peers that never import each
  other; `normalization` reaches only `extraction.models`. Checkable by grep,
  and worth checking - three of these four edges existed and were invisible.
- **Parsing:** one home (`normalization/parsing.py`) for the separator rule.
  The *compositions* stay per-caller on purpose: document text, widget text
  and dropdown labels are different input spaces.
- **Workflow states:** `EXTRACT → NORMALIZE → OPEN_ORDER →
  POPULATE_ORDER_FIELDS → ADD_ORDER_LINES → VALIDATE_ORDER →
  SAVE_AND_VERIFY_ORDER → CREATE_AND_VERIFY_INVOICE →
  APPLY_AND_VERIFY_PAYMENT → SAVE_AND_VERIFY_INVOICE → DONE`.
- **UIA go/no-go spike passed** (2026-09-04): Fakturama returns a rich,
  fully named control tree on the `uia` backend, no Java Access Bridge
  fallback needed (`probes/uia-output.txt`). Its *list grids* are the
  exception — custom-rendered, invisible to UIA, read via
  `vision_grounding` instead.
- **No selector placeholders remain.** Every `config.py` identifier is
  probed and pinned; nothing is left as an empty string.
- **Tests** cover pure logic only (normalization, `comparisons.py`,
  `matching.py`, `waits.py`, `manual_review.py`, extraction) — see
  `CLAUDE.md`'s test conventions. UI-writing code is verified live on the VM.

## Open

1. **Combo options cannot be grounded by vision bbox — this blocks every
   run.** Found live 2026-09-15 on the first post-refactor run of the golden
   sample; reproduced by `spikes/uia_probe_combo_vat_read.py`
   (`probes/probe-14-combo-vat-read.txt`). The Product VAT combo's popup is
   located correctly but is only **66x27 px**, and the vision read of that
   crop returns `[]` → `no unique VAT option matching 19%; options were []`.
   The whole-window capture ADR 0013 replaced reads the text but returns
   `bbox=(420,410,451,20)` for an option truly at `(541,537,66,27)` — ~130px
   off, which is the same mis-grounding behind the 2026-09-14 `Germany` →
   `Ghana` stop. **Neither capture mode is correct.** Prefer selecting the
   popup's items through UIA directly (it *is* a real top-level window with
   items) over clicking a vision-supplied bbox; only if that is impossible,
   crop with surrounding context and convert coordinates from the crop.
   Ignore the "DPI scaling" hypothesis in the failure message: `pywinauto`
   makes the process DPI-aware at import and `rectangle()` and
   `capture_as_image()` were measured 1:1 (1938x1048 both).
2. **The product gross price is written 100x too high, silently.** Live
   2026-09-15: `replace_text` clears the field correctly, but types
   `str(Decimal)` = `"297.50"` into a de-DE-formatted field where `.` is the
   thousands separator, leaving `29.750,00 €`. This answers the open question
   in item 17: the typed decimal separator **must** follow the field's
   locale. Silent because `_create_product`'s `verify_saved_fields` checks
   only the SKU — add the gross price to it so a mis-parse fails closed.
3. **A default Shipping is a profile precondition, and nothing says so.** A
   freshly recreated workspace has no Shipping; "Create: New Order" then
   raises a modal `Error` ("No default value found for Shippings. Please set
   one from list!") and no Order editor opens, so `OPEN_ORDER` fails with
   `no Pane control named 'New Order' found within 5.0s`. The modal is a
   *child* shell, so `app.top_level_window_by_title` cannot see it and
   nothing reports it. `entity_resolution` has no Shipping module. Either
   document it as setup or add a resolver; at minimum, detect the modal so
   the reason is the error text rather than a missing Pane.
4. **The golden sample still has no full live run.** 2026-09-15 got as far
   as: `EXTRACT` → `NORMALIZE` → `OPEN_ORDER` → `POPULATE_ORDER_FIELDS`
   (Debtor created, **Country combo selected and verified**, Payment Method
   created) → `ADD_ORDER_LINES` (VAT rate created) → stopped in
   `resolve_product`. Everything from `VALIDATE_ORDER` onward — and the whole
   match-path/populated-profile condition, including whether the Debtor
   duplication of ADR 0014 is really gone — remains unverified. Re-run once
   items 1 and 2 are fixed. `--dry-run` passes clean: every new normalization
   check (currency, ranges, completeness, confidence) accepts the sample.
5. **`Data > Documents` is unprobed** — the one screen with no VM probe at
   all. Tasks 4.5/5.5 prescribe it as an independent second check on the
   saved Order and Invoice; verification currently reads the open editor's
   own fields back instead. Probe with `spikes/uia_probe_editor.py`, then add
   a vision-grounded grid read (its rows will be UIA-invisible like every
   other Fakturama list). See ADR 0004's Consequences.
6. **Items-grid geometry on a narrow window — needs a VM check.**
   `add_order_line` measures the grid's own separator lines and requires all
   10 columns (`ORDER_LINE_GRID_COLUMNS`) to be visible in one capture. On a
   dev box during the 2026-09-06 session, horizontal scroll put Qty. and
   Discount out of view together at every position tried; a later clean run
   on a fresh process never reproduced it. Fails closed either way, so not
   unsafe — but if it recurs on the real VM, the fix is scroll-and-re-measure
   rather than one capture.
7. **Richer manual-review payloads** (deferred from Section 6, ADR 0005):
   give `ManualReviewRequired` an optional `details` payload, thread it
   through the ~10 raise sites, and add a `Decimal`/`date`-aware JSON
   encoder so a queue entry can carry the actual `NormalizedOrder`.
   `route_to_manual_review` already forwards `details` via `getattr`, so
   this is purely additive.
8. **Per-entry manual-review files** (one JSON per stuck order under
   `out/manual_review/`) plus a human-readable log, if the single
   append-only `out/manual_review_queue.jsonl` proves insufficient once a
   human or tool actually processes entries — there's no claim/delete
   workflow today. ADR 0005's Consequences.
9. **Country-code → name mapping** for the Debtor Country combo: if
   Fakturama's options are full names ("Germany") while normalized data
   holds an ISO code ("DE"), `select_exact_option` fails closed to manual
   review rather than guessing. ADR 0006.
10. **Localization** generally — accepting other number, date, and currency
   formats. `comparisons.parse_ui_date`'s month-name forms resolve through
   `LC_TIME`, which nothing sets, so a German-locale Fakturama
   (`18. Juli 2026`) would fail closed.
11. **Task-spec gaps** (Order Date, currency comparison, address read-back,
   incomplete Debtor/VAT/Payment/Product master-data fields, the stubbed OCR
   pass) — listed and ranked in
   [README.md](README.md#next-steps). Currency is now captured end-to-end
   through extraction/normalization (`RawOrder.currency` →
   `NormalizedOrder.currency`); items 9-11 below are what's still open for
   it and the other two.
12. **Order Date is extracted and normalized but never written or verified.**
    `orchestrator/steps/order_editor.py::populate_order_fields` writes only
    Cust. Ref. today. `comparisons.date_equals` already exists for the
    verify side (`verification/comparisons.py`) but is unused anywhere — it
    was built for exactly this and just needs wiring into
    `order_verification.py::_field_problems`. The write side needs a live
    VM check first: the Date edit control's locator is unconfirmed (only a
    `"Date"` label constant exists, used today to find the pricing-mode
    combo two siblings later — the date field itself, if directly
    addressable, is hypothesized at one sibling closer but never probed).
    See `.claude/plans/bug-fixes-currency-connect.md`.
13. **Currency has no UI-side verification.** Extraction/normalization
    capture it (see item 8); `verification/comparisons.py` has no
    `currency_equals`, and nothing reads a currency control off the order
    editor to compare it. Needs a live VM check first — it isn't confirmed
    Fakturama's order editor even exposes currency as a per-order control
    rather than a fixed per-installation setting; that decides whether this
    is a real check or a no-op. See
    `.claude/plans/bug-fixes-currency-connect.md`.
14. **Addresses are normalized but never verified.** `NormalizedOrder.
    billing_address`/`delivery_address` are fully populated; nothing in
    `order_verification.py` compares them. `screens.py`'s only address-
    adjacent selector is the `"Addresses"` label used to locate the Debtor-
    attach control, not the address display itself — probing is needed to
    learn whether the Order editor shows address as one free-text block or
    discrete fields before a comparator can be written. See
    `.claude/plans/bug-fixes-currency-connect.md`.
15. **`payment_details` has no UI write or verification.** It's now carried
    through normalization (ADR 0011, no longer silently dropped) but
    `ui_automation/locators.py::payment_details_pane` only exposes the
    payment-method combo and date row — nothing addresses a bank-details
    field. Whether Fakturama keeps an IBAN/BIC on the Debtor record or the
    Invoice is unconfirmed. Needs a live VM probe before a write/read-back
    path can be designed, same prerequisite as items 9-11. See
    `.claude/plans/payment-details-normalization.md`.
16. **The "Select the address" picker could match on Customer ID too.**
    `orchestrator/steps/pickers.py` still requires exactly one filtered row
    rather than checking field equality, worked around this way because its
    grid's Company column is confirmed to render clipped (unlike the Debtors
    list grid `resolve_debtor` searches, ADR 0014). Now that `resolve_debtor`
    reliably returns a real Customer ID, the picker could independently
    verify its single row's identity the same way, for a stronger guarantee
    than row-count alone.
17. **Fakturama formats money with an Arabic locale (`١٢٥`, Arabic
    currency symbol) instead of the German/EUR the pipeline assumes.**
    Found live 2026-09-14. Confirmed app-side, not glyph shaping: a
    Windows "native digits" setting cannot change the currency symbol.
    A second bug underneath it *is* fixed: the price field is pre-filled
    with a formatted 0.00 and `controls.type_text` inserts at the caret,
    so "297.50" became "297.500,00" = 297500.00 - a price 1000x too
    high, silent because `_create_product` only verifies the SKU.
    `product.py` now uses `controls.replace_text`, which fixed the
    concatenation — but live on 2026-09-15 it still produced `29.750,00 €`
    for a gross of `297.50`, because it types `"297.50"` and `.` is the
    de-DE thousands separator. **That settles the decimal-separator
    question: the typed separator must follow the field's locale.** Now
    tracked as Open item 2. Still open here: set the VM's format locale to
    de-DE (or run Fakturama under an explicit JVM locale). `spikes/uia_probe_digit_shaping.py`
    dumps the VM's locale state and what the field actually holds.
