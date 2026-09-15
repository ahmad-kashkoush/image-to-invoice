# Status and open work

Per-section status for the six components of [Doc/Design.md](Doc/Design.md)
plus the Orchestrator. This file tracks **what is real vs. still open** —
nothing else:

- *Why* the live app needed what it needed → [Doc/implementation-notes.md](Doc/implementation-notes.md)
- Decisions the design doc didn't dictate → [Doc/adr/](Doc/adr/)
- The ranked list of task-spec gaps and what I'd do with three more hours →
  [README.md](README.md#next-steps) (single source of truth; not duplicated here)

**Current state:** all seven sections implemented and committed, then
refactored (P0 pass, ADR 0009). **Verified live end to end on 2026-09-15**:
the golden sample ran through all ten workflow states to `DONE`, Order and
linked Invoice saved and verified, exit code 0, no manual-review entry - the
first full run since 2026-09-06 and the first since the refactor. That run
took every *match* path (Debtor, payment method, both Products, VAT rate);
the create paths were each exercised during the same session but not yet all
in one clean-profile run, which is Open item 1.

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
| 12 | Combo selection through UIA (replaces vision grounding) | `entity_resolution/` | `combos.py` (rewritten: `combo.select(text)` + read-back, no screenshot/vision/bbox), `debtor.py` + `product.py` (drop the now-unused `client` arg), `config.py` (`COMBO_POPUP_SETTLE_TIMEOUT_SECONDS` removed); `spikes/uia_probe_combo_vat_read.py`, `probes/probe-14-combo-vat-read.txt` | 0015 (supersedes 0013, amends 0006) |
| 13 | Number input per surface + money read-back | `normalization/`, `entity_resolution/`, `orchestrator/steps/` | `parsing.py` (`format_decimal`), `ui_automation/config.py` (`DECIMAL_SEPARATOR`), `resolver.py` (`SavedField` dataclass with optional `read`, `money_matches`), `product.py` (locale-correct price + price read-back), `vat_rate.py`, `invoice_editor.py`, `items_grid.py` | 0016 |
| 14 | Widen clipped list-grid columns before matching | `ui_automation/`, `entity_resolution/` | new `grid_columns.py` (pixel column measurement, `SIZEWE` handle probe, budgeted drag), `resolver.py::search_grid_exact` (detect clipping, widen once, re-read), `config.py` (`COLUMN_WIDEN_PIXELS`) | 0017 (completes 0014) |

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

1. **No clean-profile run yet.** 2026-09-15 reached `DONE` on a populated
   profile (every match path). The create paths all ran at some point that
   session - Debtor, both Products, VAT rate, payment method, and the Country
   combo through UIA - but never all in one run from an empty workspace, and
   the Country combo has still not run inside `_create_debtor` since ADR 0015.
   Re-run from a fresh workspace once item 2 is settled.
2. **A default Shipping is a profile precondition, and nothing says so.** A
   freshly recreated workspace has no Shipping; "Create: New Order" then
   raises a modal `Error` ("No default value found for Shippings. Please set
   one from list!") and no Order editor opens, so `OPEN_ORDER` fails with the
   misleading `no Pane control named 'New Order' found within 5.0s`. The
   modal is a *child* shell, so `app.top_level_window_by_title` cannot see it
   and nothing reports it. `entity_resolution` has no Shipping module. Either
   document it as setup or add a resolver; at minimum, detect the modal so
   the reason is the error text rather than a missing Pane. This is what
   blocks item 1.
3. **`controls.set_text` intermittently fails with "Edit stayed disabled".**
   Seen 2026-09-14 and twice on 2026-09-15, both times on the Debtor form's
   ZIP field and once on the Debtors search box, always while a stray
   `*New Debtor` editor was open from a previous failed run. No modal was
   present (checked live: `main enabled: True`, no child `Window`). It did
   not recur once the app was restarted clean, so it looks like leftover
   editor state rather than a timing problem - which means the 5s retry in
   `set_text` cannot help and raising the timeout would be the wrong fix.
   Reproduce deliberately before changing anything.
4. **The items-grid number locale is the opposite of the forms'** - see ADR
   0016's table. Only three surfaces were measured. Anything typed into a
   fourth kind of surface needs measuring, not assuming.
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
17. ~~**Fakturama formats money with an unexpected locale.**~~ **Resolved
    2026-09-15** (ADR 0016). The concatenation bug is fixed by
    `controls.replace_text`; the separator question is answered - the typed
    separator must follow the surface, and the surfaces disagree with each
    other (form Edits parse `,`, the Items grid parses `.`); and the gross
    price is now in `_create_product`'s `verify_saved_fields`, so a
    mis-parsed price fails closed where it happens. Saved Products now carry
    250.00 and 40.00 net, verified in the database. Nothing here is open;
    `spikes/uia_probe_digit_shaping.py` remains for the Arabic-digit
    rendering if it ever recurs.
