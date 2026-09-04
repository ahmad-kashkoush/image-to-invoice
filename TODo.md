
Tracks progress against `Doc/Design.md`'s six components. Scaffolding (module
layout, docstrings, signatures) exists for every component; Sections 1, 2,
and 3 have real implementations.

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
  - Tests: `tests/ui_automation/test_controls.py`, `test_waits.py`.
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
  - `debtor.py`, `product.py` — fully implemented and unit-tested (search,
    exact match, create-and-fill-form, save) against verified control
    identifiers. `product.py`'s `create()` resolves a missing VAT rate
    first, per the original scaffold's "not skipped" instruction.
  - `payment_method.py` — search half fully implemented; `create()` raises
    a specific, named error (its create form wasn't captured cleanly during
    probing — a probe gap, not a design gap).
  - `vat_rate.py` — still `raise NotImplementedError`: its list view and
    create form never rendered during probing (a stale editor was left
    open). Blocks `product.py`'s create path transitively until fixed.
  - Tests: `tests/entity_resolution/test_resolver.py`, `test_matching.py`,
    `test_debtor.py`, `test_product.py`, `test_payment_method.py`,
    `test_vat_rate.py`; `tests/ui_automation/test_vision_grounding.py`, plus
    `auto_id` coverage added to `test_controls.py`.
  - Rationale: `Doc/adr/0003-entity-resolution.md`. Plan:
    `.claude/plans/entity-resolution.md` (its "Remaining probe gap" section
    lists exactly what to re-probe on the VM to unblock VAT/Payment
    creation).

## Next (all currently `raise NotImplementedError`, uncommitted)

Suggested build order follows the state machine's own dependency chain:

1. **Residual from Section 4** — re-probe the VATs list/create form and the
   Payment create form on the Windows 11 ARM VM (per
   `.claude/plans/entity-resolution.md`'s "Remaining probe gap"), then
   implement `vat_rate.py` and `payment_method.py`'s `create()` for real.
   Also verify the `ComboBox.select(...)` option strings guessed in
   `debtor.py` (Country) and `product.py` (VAT) — never confirmed against
   Fakturama's real dropdown contents (see ADR 0003, Consequences).
2. **Section 5 — Verification** (`verification/`)
   - `order_verification.py`, `invoice_verification.py`,
     `payment_verification.py` — read live UI state back rather than trusting
     the save/create action succeeded. Expect to reuse
     `ui_automation/vision_grounding.py`: probing found the Order editor's
     line grid, customer field, and payment control are also UIA-invisible.
3. **Section 6 — Error Handling** (`error_handling/`)
   - `manual_review.py::route_to_manual_review` — write manual-review queue
     entries (source image, failed step, reason, partial state) to the
     shared `out` folder per the README layout.
4. **Orchestrator** (`orchestrator/state_machine.py::run_workflow`)
   - Implement the 9-state loop (EXTRACT → NORMALIZE → OPEN_ORDER →
     POPULATE_ORDER_FIELDS → ADD_ORDER_LINES → VALIDATE_ORDER →
     SAVE_AND_VERIFY_ORDER → CREATE_AND_VERIFY_INVOICE →
     APPLY_AND_VERIFY_PAYMENT), catching `ManualReviewRequired` at the top
     level. This is the integration point — do it last, once 1–3 are real.
     Note: probing found the Order editor's own line grid, customer field,
     and payment control are not exposed to UIA either (`probes/probe-01/02-*.txt`)
     — order-line entry will need the same vision-grounding/keyboard
     approach as entity search, not `find_control` selectors.

## Not started / not yet stubbed

- Real control names/`auto_id`s for the Order editor, Invoice editor, and
  the VATs/Payment create forms — the Order/Invoice editor was probed
  (`probes/probe-00/01/02-*.txt`) and found largely UIA-invisible (see
  above); VATs and Payment's create form were not captured cleanly (see
  "Residual from Section 4" above). Use `spikes/uia_probe_editor.py
  <keyword>` (or a full `spikes/uia_probe.py` dump — see
  `.claude/plans/entity-resolution.md`'s Gate section for why a full dump
  beats a keyword-filtered one for blank-named controls) against each live
  editor/dialog as Section 5/orchestrator implementation reaches it.

## Future work

- Localization, and accepts different formats to numbers, dates, currencies,..., etc.
