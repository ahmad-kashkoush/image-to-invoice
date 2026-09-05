
Tracks progress against `Doc/Design.md`'s six components. Scaffolding (module
layout, docstrings, signatures) exists for every component; Sections 1-5
have real implementations.

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
  - Tests: `tests/entity_resolution/test_resolver.py`, `test_matching.py`,
    `test_debtor.py`, `test_product.py`, `test_payment_method.py`,
    `test_vat_rate.py`; `tests/ui_automation/test_vision_grounding.py`, plus
    `auto_id` coverage added to `test_controls.py`.
  - **Still open:** the two `ComboBox.select(...)` calls (`debtor.py`
    Country, `product.py` VAT) still pass guessed option strings, never
    confirmed against Fakturama's real dropdown contents (ADR 0003,
    Consequences) — probing the combos directly turned out to be its own
    problem: a captured dropdown popup came back with zero child
    controls, the same UIA-opacity signature as the list grids. See
    `.claude/plans/entity-resolution-residual.md` for what's confirmed vs.
    still an open design question (a vision-grounded combo reader may be
    needed, the same fallback the list grids use).
  - Rationale: `Doc/adr/0003-entity-resolution.md`. Plan:
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
  - Tests: `tests/verification/test_comparisons.py`,
    `test_order_verification.py`, `test_invoice_verification.py`,
    `test_payment_verification.py` — duck-typed window/control fakes and a
    fake vision client, no real window/screenshot/network, using the
    golden `WEB-2026-0714-A17` sample order as the known-good fixture.
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

## Next (all currently `raise NotImplementedError`, uncommitted)

Suggested build order follows the state machine's own dependency chain:

1. **Residual from Section 4 (down to one item)** — VAT and Payment are
   both now fully probed and implemented (see Section 4's Done entry
   above). What's left: resolve whether the Product VAT / Debtor Country
   combos are UIA-readable at all, and either confirm real option strings
   for the current guessed `.select()` calls, or design a vision-grounded
   combo reader if they turn out to be as UIA-opaque as the list grids —
   see `.claude/plans/entity-resolution-residual.md`.
2. **Orchestrator** (`orchestrator/state_machine.py::run_workflow`)
   - Implement the 9-state loop (EXTRACT → NORMALIZE → OPEN_ORDER →
     POPULATE_ORDER_FIELDS → ADD_ORDER_LINES → VALIDATE_ORDER →
     SAVE_AND_VERIFY_ORDER → CREATE_AND_VERIFY_INVOICE →
     APPLY_AND_VERIFY_PAYMENT), catching `ManualReviewRequired` at the top
     level. This is the integration point — do it last, once 1–2 are real.
     Note: probing found the Order editor's own line grid, customer field,
     and payment control are not exposed to UIA either (`probes/probe-01/02-*.txt`)
     — order-line entry will need the same vision-grounding/keyboard
     approach as entity search, not `find_control` selectors.

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
- Whether the Product VAT / Debtor Country ComboBox dropdowns are
  UIA-readable at all — see "Residual from Section 4" above and
  `.claude/plans/entity-resolution-residual.md`.
- Verifying via Data > Documents itself (Task 4.5/5.5's own prescribed
  check — a second, independent read distinct from reading the editor's
  internal fields) — not implemented; would need its own vision-grounded
  grid read once the pane above is probed. See
  `Doc/adr/0004-verification.md`'s Consequences.

## Future work

- Localization, and accepts different formats to numbers, dates, currencies,..., etc.
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
