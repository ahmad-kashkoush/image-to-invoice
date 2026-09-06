# 0009. Refactoring P0: dependency direction, one selector home, and honest states

## Status

Accepted (2026-09-06). Verified by import/compile checks and a direct
exercise of the failure path; **not yet re-verified by a live VM run** — see
Consequences.

Supersedes parts of `0004` (Decisions 2/3's selector *location*), `0007`
(Decision 2's single `actions.py`), and `0008` (Decision 5's deliberate
duplicate literal). Restores `0007` Decision 3, which the implementation had
drifted away from.

## Context

The system reached a working end-to-end path (`TODo.md`, `0008`) and is now
being prepared for review. A full architectural read of the repo produced a
ranked list of problems (`.claude/plans/refactoring-architecture-review.md`);
this ADR records the six marked **P0 — must refactor**, which are the ones
that affected correctness, dependency direction, or how the system reads to
someone opening it for the first time.

Four findings drove the work. All four were measured, not assumed:

1. **The process exited 0 on failure.** `__main__.main()` discarded
   `run_workflow`'s return value, and `run_workflow` swallows every
   `ManualReviewRequired` by design. An order that stopped at `normalize`
   and one that reached `DONE` were indistinguishable to the shell: both
   exited 0, both printed nothing. A fail-open at the outermost boundary of
   a system whose entire thesis is failing closed.

2. **Two states ran checks that could not fail.** `VALIDATE_ORDER` called
   `check_required_fields(order)`, and the `ADD_ORDER_LINES` loop re-ran
   `check_line_total(item)` — both on the record `normalize_order` had
   already validated and raised on. Neither could ever fire.
   `VALIDATE_ORDER`'s own docstring meanwhile claimed it "validate[s]
   addresses, products, and the overall total before saving" (Task 4.1/4.3),
   which it did not do at all.

3. **`ui_automation` contradicted its own ADR.** `0007` Decision 3 states
   the package "is not `error_handling`-aware and should not become so", yet
   `vision_grounding.py` raised `ManualReviewRequired` at 15 sites and
   `grid_geometry.py` at 6 — with a hardcoded default step string, so a
   failed grid read reached the review queue labelled
   `"ui_automation.read_grid_rows"` instead of the workflow step that was
   running.

4. **Selectors were partitioned by consuming section, not by screen.**
   Order-editor knowledge lived in `verification/config.py` (field names,
   tab titles, read-back columns), `orchestrator/config.py` (label anchors,
   the rendered column list) and as literals inside
   `comparisons.line_row_problems`. Two visible costs: `"New Invoice"` had
   to be declared twice with `0008` Decision 5 explaining why the
   duplication was necessary, and the Items grid was described in three
   places that had to be kept in sync by hand.

Two further problems were domain-level: `NormalizedLineItem.recomputed_total`
was a mutable field the normalizer assigned *after* construction (every
order-level total, and the payment Value written into Fakturama, derives
from it — a line item built any other way silently contributed 0.00), and
the PAID-status rule was implemented independently at the site that writes
payment and the site that verifies it.

## Decisions

**1. The CLI reports the run's outcome on the process exit code.**
`main()` returns 0 for `WorkflowState.DONE` and 1 otherwise, naming the
step it stopped at and the queue file on stderr. `run_workflow`'s contract
is unchanged — it still never lets a `ManualReviewRequired` escape — but its
return value is now actually consumed. Chosen over making `run_workflow`
re-raise, which would have moved the queue-then-stop decision out of the one
place that owns it.

**2. `VALIDATE_ORDER` reads the UI; the two unreachable checks are deleted.**
`verification.order_verification.verify_order_before_save` compares the
Order editor's own Cust.Ref. and its Total Net / VAT / Total — which
Fakturama computed itself from the lines just entered — against the totals
derived from the normalized record, and fails closed on any mismatch.

This is the first check in the workflow that can catch a *whole-order*
problem: a line that reached the grid but not the totals, a non-zero
order-level discount or shipping charge, a pricing mode that reverted to
Gross. No per-line check can see any of those. It deliberately does not
re-read the item grid (a vision call): every line was already compared
column by column immediately after entry, and the totals are the aggregate
signal for them.

The alternative — delete the state and fold everything into
`SAVE_AND_VERIFY_ORDER` — was rejected because Task 4.3 asks for the totals
to be confirmed *before* the save, and because a check that runs while the
order is still fixable is worth more than the same check afterwards.

Addresses (also part of Task 4.1) remain unverified; the address field is a
multi-line Edit that has never been probed for read-back. That gap is
recorded in the function's docstring and `README.md`'s Next Steps rather
than papered over.

**3. `ui_automation` raises only mechanical failures.**
`GridReadError` and `GridGeometryError` join `ControlNotFoundError` /
`AmbiguousControlError` / `DialogTimeoutError` / `WindowFocusError` in
`ui_automation/exceptions.py`, and the state machine converts all six at the
one boundary that knows which step is running. The `step` parameter
those two modules threaded through their public functions is gone — deciding
what a failure *means* is not their job.

`ui_automation` now imports nothing from this project outside itself, which
is a stronger property than `0007` Decision 3 originally asked for and is
worth keeping deliberately: it is the layer everything else sits on.

While doing this, `vision_grounding`'s three public reads
(`read_grid_rows`, `read_grid_rows_located`, `read_combo_options`) were
collapsed onto one `_read_via_vision_tool` helper. They were ~200 lines of
three-way copy-paste of the same call → refusal → tool-block → parse
sequence, differing only in schema, prompt and result shape.

**4. Every Fakturama selector lives in `ui_automation/screens.py`, by
screen.** A selector describes a screen, not whichever section needed it
first, and the write path and the read-back path need identical answers —
the payment-method combo verification reads is the one the payment step
sets. `screens.py` imports nothing, so any layer may read it. Timeouts,
retry counts and settle delays stay in each package's own env-driven
`config.py`; those are genuine per-section tunables.

Two consequences fall out rather than being separately fixed:
`"New Invoice"` is now declared once (superseding `0008` Decision 5, whose
reasoning was sound for the arrangement it was written under), and the Items
grid is described once — the read-back subset and the fill subset are both
*selected* from the rendered column list through a helper that raises at
import time on a name that grid does not have, so the three hand-maintained
lists cannot drift.

The structural lookups for blank-named controls
(`items_grid_pane`, `payment_details_pane`, `payment_method_combo`,
`payment_date_edit`) moved from `verification/readback.py` to
`ui_automation/locators.py` for the same reason. This was ranked P1, but
P0-4's boundary is not actually achieved without it: the write path was
importing the *verification package* to find its own controls.

**5. `orchestrator/actions.py` (815 lines) splits into
`orchestrator/steps/`, by screen.** `order_editor.py`, `invoice_editor.py`,
`items_grid.py`, `pickers.py`, `toolbar.py`, none over ~255 lines, with
`steps/__init__.py` exporting the seven actions the state loop calls.

The seam is by screen, with two deliberate exceptions:

- `pickers.py` imports neither editor. It takes the button that opens the
  dialog and a callback describing a wrong row count, so the two very
  different callers share one implementation of a protocol that took three
  rounds of live debugging to get right.
- `items_grid.py` is separate from `order_editor.py` because it is a
  different *mechanism*, not just a different part of the same screen —
  measure separator lines, compute a coordinate, click, type blind, read the
  row back through a vision call — and it is the only place in the codebase
  that writes without a control to write to.

Generic mechanics moved down into `ui_automation.controls`:
`reactivate_editor` (the Eclipse tab-reactivation retry, needed by both
editors) and `window_still_exists` (the COMError-tolerant existence check).
No logic was changed and no docstring rewritten *in the move* — those
docstrings are the live-debugging record, and moving and rewriting in one
commit would have made the diff unreviewable.

A separate pass afterwards thinned the prose across the files this refactor
created or rewrote (~400 lines), removing refactor archaeology, bug
narratives already told in full in `Doc/implementation-notes.md`, and
docstrings restating their own signature. The live-debugging facts themselves
were kept wherever a reader could otherwise delete the code without knowing
why it exists — the picker's auto-close, Net pricing being mandatory,
`window_text()` returning the label, the clipped Company column, the gross
price field. `ui_automation/screens.py` stayed comment-dense on purpose: those
comments *are* the probe record, and are what a re-probe would check against.

**6. The two money invariants are enforced by construction.**
`NormalizedLineItem.recomputed_total` is a computed property, not a field the
normalizer fills in afterwards; `validators.recompute_line_total` delegates
to it, so Task rule 3.16 is still written in exactly one place and still has
its named, importable form. `NormalizedOrder.is_paid` is the single
interpretation of the PAID status string, read by both the payment step and
the payment verification.

Chosen over a frozen dataclass or a private constructor: the goal was to
make the two rules that money depends on unable to be wrong, not to make the
type harder to build in tests.

## Consequences

- **A failed run is now visible.** Verified directly: an unsupported image
  type exits 1, prints the step and the queue path to stderr, and appends
  the entry. The exit code is what a batch driver or CI would key on.
- **No state performs a check that cannot fail**, and no manual-review entry
  can be filed under a module name — `_UI_DISCOVERY_ERRORS` relabels every
  mechanical failure with the real `WorkflowState`.
- **`VALIDATE_ORDER` can now stop an order that previously passed.** That is
  the point, but it means the first live run after this change must be on
  the known-good golden order: a stop there needs to be reproduced and
  explained, not worked around.
- **Not yet verified live.** Everything here was checked by importing every
  module, compiling the tree, exercising the failure path end to end, and
  confirming the read/fill column lists are byte-identical to before (so the
  vision prompts are unchanged). None of that touches a real Fakturama
  window, and per `CLAUDE.md` nothing that does can be unit tested. **A full
  live run to `DONE` on the golden order is the outstanding gate for this
  ADR**, and should exercise both a clean profile (every create path) and a
  populated one (every match path).
- `verification` still imports `entity_resolution.matching.parse_vat_text`,
  and `normalization.validators` still imports from
  `extraction.vision_extractor` (which pulls in the Anthropic SDK). Both are
  real dependency-direction problems; both were ranked P1 and are not
  addressed here. They are the whole content of the next sub-plan.
- `ORDER_CUST_REF_EDIT_NAME` and `INVOICE_CUST_REF_EDIT_NAME` still hold the
  same literal, as do the two Total field names. Kept separate on purpose:
  they are independent facts about two screens that happen to agree today,
  and collapsing them would assert a relationship no probe established.
- A few probed selectors in `screens.py` have no caller yet
  (`DEBTOR_FORM_CUSTOMER_ID_AUTO_ID`, `ORDER_DISCOUNT_EDIT_NAME`,
  `LIST_EDITOR_TAB_AUTO_ID`). They are kept as probe inventory — the first
  is exactly the identifier the Debtor-matching fix (README's Next Steps)
  needs.
- `waits.wait_for_dialog`, `waits.wait_for_stable_row_count` and
  `verification.config.VERIFY_SETTLE_SECONDS` have no production caller.
  That predates this refactor; noted rather than removed, since removing the
  first two would also remove `tests/ui_automation/test_waits.py`'s reason
  to exist. Tracked as P2.
