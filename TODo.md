# Status and open work

Per-section status for the six components of [Doc/Design.md](Doc/Design.md)
plus the Orchestrator. This file tracks **what is real vs. still open** —
nothing else:

- *Why* the live app needed what it needed → [Doc/implementation-notes.md](Doc/implementation-notes.md)
- Decisions the design doc didn't dictate → [Doc/adr/](Doc/adr/)
- The ranked list of task-spec gaps and what I'd do with three more hours →
  [README.md](README.md#next-steps) (single source of truth; not duplicated here)

**Current state:** all seven sections implemented and committed, then
refactored (P0 pass, ADR 0009). Verified live on the VM (2026-09-06): a full
run from the order image through all ten workflow states to `DONE`, Invoice
saved and verified (`INV000001`), no manual-review entry — **that run predates
the refactor; re-running it is Open item 1.**

## Done

| # | Section | Package | Files | ADR |
|---|---|---|---|---|
| 1 | Image Extraction | `extraction/` | `vision_extractor.py` (Claude Haiku 4.5 vision pass), `ocr_fallback.py` (deliberate no-op stub), `models.py`, `config.py`, `__init__.py::extract_order` | — |
| 2 | Normalization & Validation | `normalization/` | `normalizer.py`, `validators.py`, `models.py`, `config.py` | 0001 |
| 3 | UI Control Discovery | `ui_automation/` | `controls.py`, `waits.py`, `app.py`, `exceptions.py`, `config.py`; `vision_grounding.py` + `grid_geometry.py` added later (see 4 and 7); `spikes/uia_probe.py`, `spikes/uia_probe_editor.py`, `probes/*.txt` | 0002 |
| 4 | Entity Resolution | `entity_resolution/` | `resolver.py`, `debtor.py`, `product.py`, `vat_rate.py`, `payment_method.py`, `matching.py`, `combos.py`, `models.py`, `config.py` | 0003, 0006 |
| 5 | Verification | `verification/` | `order_verification.py`, `invoice_verification.py`, `payment_verification.py`, `comparisons.py`, `readback.py`, `config.py` | 0004 |
| 6 | Error Handling | `error_handling/` | `manual_review.py`, `exceptions.py`, `config.py` | 0005 |
| 7 | Orchestrator | `orchestrator/` | `state_machine.py`, `actions.py`, `config.py`, `__main__.py` | 0007 |
| 7b | `SAVE_AND_VERIFY_INVOICE` (tenth state) | `orchestrator/`, `verification/` | `state_machine.py`, `actions.py::save_invoice`, `invoice_verification.py::verify_invoice_saved`, `payment_verification.py::payment_problems` | 0008 |
| 8 | P0 refactor: dependency direction, one selector home, honest states | all | new `ui_automation/screens.py` + `locators.py`; `actions.py` → `orchestrator/steps/{order_editor,invoice_editor,items_grid,pickers,toolbar}.py`; `__main__.py` (exit code), `state_machine.py`, `normalization/models.py` (computed `recomputed_total`, `is_paid`), `ui_automation/{exceptions,vision_grounding,grid_geometry,controls}.py`, all three `config.py` trimmed to tunables | 0009 (amends 0004, 0007, 0008) |

Notes worth keeping in one place:

- **Selectors:** every Fakturama control identifier lives in
  `ui_automation/screens.py`, by screen, and nothing else declares one. Each
  package's `config.py` holds only timeouts/retry counts.
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

1. **Re-run the golden sample order live, post-refactor.** The P0 pass (ADR
   0009) touched every package. It is verified by import/compile of the whole
   tree, by the failure path end to end (exit code 1 + queue entry), and by
   the vision-read column lists coming out byte-identical — but nothing there
   touches a real Fakturama window, and per `CLAUDE.md` nothing that does can
   be unit tested. Run on a clean profile (exercises every create path) and on
   a populated one (every match path). `VALIDATE_ORDER` now reads the UI and
   can stop an order that previously passed: a stop there must be reproduced
   and explained, not worked around.
2. **`Data > Documents` is unprobed** — the one screen with no VM probe at
   all. Tasks 4.5/5.5 prescribe it as an independent second check on the
   saved Order and Invoice; verification currently reads the open editor's
   own fields back instead. Probe with `spikes/uia_probe_editor.py`, then add
   a vision-grounded grid read (its rows will be UIA-invisible like every
   other Fakturama list). See ADR 0004's Consequences.
3. **Items-grid geometry on a narrow window — needs a VM check.**
   `add_order_line` measures the grid's own separator lines and requires all
   10 columns (`ORDER_LINE_GRID_COLUMNS`) to be visible in one capture. On a
   dev box during the 2026-09-06 session, horizontal scroll put Qty. and
   Discount out of view together at every position tried; a later clean run
   on a fresh process never reproduced it. Fails closed either way, so not
   unsafe — but if it recurs on the real VM, the fix is scroll-and-re-measure
   rather than one capture.
4. **Richer manual-review payloads** (deferred from Section 6, ADR 0005):
   give `ManualReviewRequired` an optional `details` payload, thread it
   through the ~10 raise sites, and add a `Decimal`/`date`-aware JSON
   encoder so a queue entry can carry the actual `NormalizedOrder`.
   `route_to_manual_review` already forwards `details` via `getattr`, so
   this is purely additive.
5. **Per-entry manual-review files** (one JSON per stuck order under
   `out/manual_review/`) plus a human-readable log, if the single
   append-only `out/manual_review_queue.jsonl` proves insufficient once a
   human or tool actually processes entries — there's no claim/delete
   workflow today. ADR 0005's Consequences.
6. **VM verification for `combos.py`'s two coordinate-click assumptions**
   (not blocking — both fail closed): that screenshot pixels map 1:1 to
   screen coordinates (no DPI scaling), and that a dropdown renders inside
   `main_window`'s rectangle. ADR 0006.
7. **Country-code → name mapping** for the Debtor Country combo: if
   Fakturama's options are full names ("Germany") while normalized data
   holds an ISO code ("DE"), `select_exact_option` fails closed to manual
   review rather than guessing. ADR 0006.
8. **Localization** generally — accepting other number, date, and currency
   formats. `comparisons.parse_ui_date`'s month-name forms resolve through
   `LC_TIME`, which nothing sets, so a German-locale Fakturama
   (`18. Juli 2026`) would fail closed.
9. **Task-spec gaps** (Order Date, currency comparison, address read-back,
   Debtor matching by Customer ID, incomplete Debtor/VAT/Payment/Product
   master-data fields, the stubbed OCR pass) — listed and ranked in
   [README.md](README.md#next-steps).
