
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
    import Application` fails off Windows, confirmed) — **unverified by me,
    pending a run on the Windows 11 ARM VM against real Fakturama** (README's
    build-order step 1, the go/no-go gate). `controls.py`/`waits.py` need no
    such verification: they never import `pywinauto`, so they're fully unit
    tested now.
  - Tests: `tests/ui_automation/test_controls.py`, `test_waits.py`.
  - Rationale: `Doc/adr/0002-ui-automation-testability-boundary.md`.

## Next (all currently `raise NotImplementedError`, uncommitted)

Suggested build order follows the state machine's own dependency chain:

1. **Section 4 — Entity Resolution** (`entity_resolution/`)
   - `resolver.py::resolve_exact_or_create` — shared search-then-create shape.
   - `debtor.py`, `product.py`, `vat_rate.py`, `payment_method.py` — wire each
     to the resolver using `ui_automation` (depends on Section 3).
2. **Section 5 — Verification** (`verification/`)
   - `order_verification.py`, `invoice_verification.py`,
     `payment_verification.py` — read live UI state back rather than trusting
     the save/create action succeeded.
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

## Not started / not yet stubbed

- No tests exist yet outside `tests/extraction/`, `tests/normalization/`,
  and `tests/ui_automation/`.
- `app.py` and `spikes/uia_probe.py` need a real run against a live
  Fakturama window on the Windows VM — see Section 3's note above.

## Future work

- Localization, and accepts different formats to numbers, dates, currencies,..., etc.
