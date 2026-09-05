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
