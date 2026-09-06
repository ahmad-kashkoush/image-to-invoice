# Fakturama Automation — working conventions

This file records conventions established while building this project, so
future sections stay consistent with earlier ones without re-deriving them.
Background: `README.md` (project overview, platform, build order) and
`Doc/Design.md` (architecture, six components + orchestrator).

## Planning

Whenever a task is planned (via plan mode, or a direct "write the plan for
X" request), save the final plan as a markdown file in this repo's
`.claude/plans/` directory — not only in the harness's default global
`~/.claude/plans/` location, which is outside the repo and not visible to
anyone else working on it. Name the file for the section/feature it covers
(e.g. `extraction-module.md`, `ui-control-discovery.md`), matching the
existing files in that directory. Do this automatically, without being
asked each time.

## Section model

The design (`Doc/Design.md`) and `TODo.md` define six components — Image
Extraction, Normalization & Validation, UI Automation, Entity Resolution,
Verification, Error Handling — plus an Orchestrator that ties them together.
Every module ships scaffolded first (docstrings + signatures that
`raise NotImplementedError`) before being implemented section by section, in
the dependency order `TODo.md` lists. Check `TODo.md`'s "Open" list before
starting new work — it tracks what's real vs. still a stub. Keep that file
short: it is a status list, not a narrative. Findings belong in
`Doc/implementation-notes.md`, decisions in an ADR, and the ranked list of
task-spec gaps lives only in `README.md`'s Next Steps.

**Per-section wrap-up ritual** (do all of these when a section moves from
stub to real, not just the code):
1. Implement the section.
2. Add a section to `Doc/implementation-notes.md` — what was actually
   decided, not a restatement of the design (see that file's existing
   sections for the pattern: one `##` per module or workflow state, oldest
   first). These used to live in `Doc/Design.md`; they were split out so the
   design doc stays at its delivered size. Leave a one-line pointer in the
   relevant `Doc/Design.md` section only if that section has none yet.
3. Write an ADR under `Doc/adr/NNNN-title.md` for any decision that wasn't
   fully dictated by the design doc or task description (see
   `Doc/adr/0001-normalization-and-validation.md` for the template:
   Status / Context / Decisions / Consequences).
4. Add the section to `TODo.md`'s "Done" table (one row: section, package,
   files touched, ADR numbers) and drop anything it closes from the "Open"
   list, renumbering what remains.
5. Suggest bulk commit message following conventional commits pattern.

## Fail-closed, not best-effort

The system's central principle (`Doc/Design.md`'s Tradeoffs section):
wherever a decision has a definite correct answer — a line total, an exact
match, whether a save persisted — use deterministic rules, and stop rather
than guess when a value is missing, ambiguous, or low-confidence. This
shows up concretely as:

- `error_handling.exceptions.ManualReviewRequired(step, reason)` is the
  single exception type that routes to manual review. Raise it (don't
  return `None`/a sentinel/a partially-valid object) whenever a step cannot
  safely proceed.
- Prefer **aggregating** every failure found in one pass into one
  `ManualReviewRequired` with a combined reason, rather than raising on the
  first problem — manual review should see the whole picture for one
  order/step at once. See `normalization/normalizer.py::normalize_order`.
- Entity resolution is exact-match only, never fuzzy — a wrong match (e.g.
  attaching an order to the wrong Debtor) is a worse failure than routing
  to creation or manual review.
- A missing confidence score for a field that *was* extracted is treated as
  0.0 (fail closed), never assumed to be a confident read.

## Parsing conventions (normalization and beyond)

- **Dates**: canonical form is ISO `YYYY-MM-DD`. Parse ISO first; a
  `DD.MM.YYYY` fallback is supported for the German-locale deployment
  target. An ambiguous format (e.g. a slash date that could be
  `MM/DD/YYYY` or `DD/MM/YYYY`) is never guessed — it fails closed.
- **Money**: `Decimal`, not `float`, quantized to 2 decimal places
  (`ROUND_HALF_UP`). Parsing tolerates both dot-decimal and European
  comma-decimal input (`1.234,56`), with currency symbols/thousands
  separators stripped.
- **Percentages** (VAT, discount): stored as plain numbers (e.g. `19`, not
  `"19%"` or `0.19`).
- **Line total formula** (Task rule 3.16, `validators.recompute_line_total`):
  `quantity * unit_net_price * (1 - discount / 100)`. Discount is a
  percentage; VAT is excluded from the net line total. Keep this formula in
  exactly one place — anything that needs it should import it, not
  reimplement it.

## Config pattern

Each section that needs tunables gets its own small, env-driven
`config.py` (see `extraction/config.py`, `normalization/config.py`):
module-level constants read via `os.environ.get(...)` with a sensible
default, no framework, so tests can override behavior by constructing
values directly rather than mutating global state.

## Test conventions

Tests are no longer required per section — the duck-typed pywinauto/UI-fake
test suite was removed as low-value (2026-09-06). What remains covers only
pure, no-mock logic: normalization (`normalizer.py`/`validators.py`),
verification's comparison helpers (`comparisons.py`), entity resolution's
`matching.py`, UI automation's `waits.py` (no pywinauto import), error
handling's `manual_review.py`, and extraction's `vision_extractor.py`/
`ocr_fallback.py` (network calls faked via an injectable `client` keyword
param — a sanctioned exception, not "UI-fake").

- Don't add new tests for UI-writing code — anything that touches a real
  `pywinauto` control/window (entity_resolution's per-entity form-filling,
  `ui_automation.controls`/`vision_grounding`, `verification`'s
  order/invoice/payment checks, the orchestrator's state machine/actions).
  That class of test was judged not worth its maintenance cost; verify
  those changes live on the VM instead.
- If you do add a test for genuinely pure logic, keep it under
  `tests/<section>/`, mirroring `src/fakturama_automation/<section>/` (no
  `__init__.py`, no `pytest.ini` — plain rootdir discovery), and prefer a
  golden fixture (e.g. the assessment's `WEB-2026-0714-A17` sample order,
  Northstar Office GmbH / EUR / net line totals 450.00 + 120.00 = 570.00
  net) over a synthetic one when a section has one.

## Platform note

This automates a Windows desktop app (Fakturama) via `pywinauto`'s `uia`
backend inside a Windows 11 ARM VM — see `README.md`'s Platform/VM Setup
sections. `pywinauto` will not import on macOS/Linux, so any module that
imports it (`ui_automation/`, and anything that transitively imports it)
cannot be unit tested outside the VM. Extraction and normalization have no
such dependency and are developed/tested cross-platform by design (see
`README.md`'s "Suggested build order").
