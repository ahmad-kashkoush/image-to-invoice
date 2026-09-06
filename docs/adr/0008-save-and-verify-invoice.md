# 0008. Save & verify the Invoice as its own workflow state

## Status

Accepted

## Context

The workflow's last state was `APPLY_AND_VERIFY_PAYMENT`: set the Invoice's
payment method, and when the order is PAID also the paid toggle, payment
date and full Value, then re-read all of it back with
`verification.payment_verification.verify_payment_applied` and return
`DONE`. Nothing ever clicked Save on the Invoice - `orchestrator.actions.
save_order` is Order-only, and no other action in that module saves
anything.

This was not noticed for a long time because it fails invisibly: every
verification passed, no `ManualReviewRequired` was raised, and the run
reported success. What it verified, though, was the contents of an *open
editor*, which is not the same thing as a persisted document. Confirmed
live across two runs of the same order image:

- Run A ended `DONE` with every check green; `FKT_DOCUMENT` contained the
  saved Order but no Invoice row at all, and the editor tab was still
  titled "New Invoice". The applied payment data existed only in the UI.
- Run B looked identical from the automation's side, but the Invoice *was*
  persisted as `INV000001` with `PAID=TRUE`, `PAYDATE='2026-07-18'`,
  `PAIDVALUE=678.3` - because a human clicked Save by hand after watching
  the run finish.

So the pipeline's final state depended on an operator happening to save,
and its own success signal could not tell the two runs apart. That is
precisely the failure mode `Doc/Design.md`'s fail-closed principle exists
to prevent: "whether a save persisted" has a definite correct answer and
must be checked, not assumed.

## Decisions

**1. Add a tenth state, `SAVE_AND_VERIFY_INVOICE`, rather than folding the
save into `APPLY_AND_VERIFY_PAYMENT`.** The workflow's shape is one
`act -> verify -> advance` per state, and `SAVE_AND_VERIFY_ORDER` already
establishes that persisting a document is a state of its own with its own
verification, distinct from the state that populated it. Folding a save
plus a second read-back into the payment state would have made one state
carry two act/verify pairs, and would have reported a save failure under
the payment step's name in the manual review queue.

**2. `actions.save_invoice` re-activates the editor first;
`actions.save_order` does not.** The main toolbar's Save button acts on
whichever editor is active. When the Order is saved it is trivially the
active tab, so `save_order` just clicks. By the Invoice save, two editors
are open and `verify_payment_applied` has been reading controls in
between, so the Invoice tab is re-activated through the existing
`_reactivate_editor` helper - which retries until one of the editor's own
controls is findable, rather than trusting that `set_focus()` took (the
Eclipse behaviour documented in `0007`). Probing for the Invoice's
"Cust.Ref." field is unambiguous despite the Order editor having an
identically named field, because Eclipse only exposes the *active* tab's
contents to UI Automation. The shared toolbar click itself moved into one
private `_click_save` used by both.

**3. `verify_invoice_saved` checks persistence, Cust.Ref., Total and every
payment field - but deliberately does not re-read the item grid.** The
grid read is a vision-model call, the lines were verified against the same
normalized record moments earlier by `verify_invoice_matches_order` in the
preceding state, and a save is not a line-editing operation. The Total
field is the aggregate signal that would catch a line the save somehow
altered. The rule applied here is that a verification checks what *its own
step* is responsible for - persistence, and that the just-applied payment
data went to the database with it - rather than re-establishing everything
already proven before it.

**4. The payment checks are shared by extraction, not duplicated or
re-raised.** `payment_verification.payment_problems` was split out of
`verify_payment_applied`, which now formats and raises from it.
`verify_invoice_saved` calls the same function and folds its strings into
its own aggregated `ManualReviewRequired`. The alternative - calling
`verify_payment_applied` and catching its exception - would have filed a
post-save failure under the step name `verify_payment_applied`, pointing a
reviewer at the wrong step.

**5. "Saved" is detected by the tab title, mirroring the Order.** An
Invoice tab reads "New Invoice" until saved, then becomes the assigned
invoice number, so `verification/config.py` gains
`INVOICE_TAB_TITLE_UNSAVED` next to the existing
`ORDER_TAB_TITLE_UNSAVED`. It duplicates the literal in
`orchestrator/config.py`'s `INVOICE_EDITOR_PANE_NAME` (which uses it to
*locate* the still-unsaved pane) rather than importing it, because
verification must not depend on the orchestrator - that dependency runs
the other way.

> **Amendment (2026-09-06, later the same day).** The duplication this
> Decision reasoned its way into is gone, and the reasoning is why: both
> declarations were symptoms of selectors being partitioned by *consuming
> section* rather than by *screen*. `"New Invoice"` is now declared once, in
> `ui_automation/screens.py`, which sits below both packages - so locating
> the unsaved pane and detecting that it has been saved read the same
> constant without either package depending on the other. Decisions 1-4 are
> unchanged. See `0009`.


## Consequences

- Verified live (2026-09-06): a full run from the order image completed
  end to end through the new state, saving and verifying the Invoice
  without human intervention and without a manual-review entry.

- The workflow now reports `DONE` only for an Invoice that is actually in
  the database with its payment data intact. A run that previously ended
  green with nothing persisted now fails closed to manual review under
  `save_and_verify_invoice`.
- Two read-backs of the payment fields now happen per run (before and
  after the save). They are cheap UIA property reads, no vision call.
- Recorded demos made before this change show the operator saving the
  Invoice by hand at the end; that step is now part of the automation and
  those recordings are out of date.
- `payment_problems` is now part of `payment_verification`'s surface, not
  a private helper - a second caller in another module depends on it.
