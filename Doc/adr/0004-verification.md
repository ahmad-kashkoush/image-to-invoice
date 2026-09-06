# 0004. Verification: aggregate-then-raise, name-based Order/Invoice selectors, and probe-gap placeholders (Section 5)

## Status

Accepted. Decision 3 and parts of Consequences overtaken — see Amendment
(2026-09-06).

> **Amendment (2026-09-06).** Decisions 1, 2, 4 and 5 still hold.
>
> - **Decision 3's placeholders are gone.** All six selectors
>   (`ORDER_ITEMS_GRID_PANE_AUTO_ID`, `INVOICE_ITEMS_GRID_PANE_AUTO_ID`,
>   `INVOICE_PAYMENT_METHOD_COMBO_NAME`, `INVOICE_PAID_CHECKBOX_NAME`,
>   `INVOICE_PAYMENT_DATE_EDIT_NAME`, `INVOICE_PAYMENT_VALUE_EDIT_NAME`)
>   were probed and pinned in a later VM session; nothing in
>   `verification/config.py` is left as `""` with a `# TODO probe`. The
>   fail-closed rationale for *why* they were placeholders stands as a
>   record; the state it describes does not.
> - The Invoice editor's field layout is no longer "assumed" — a full live
>   run has read those fields back (`Doc/implementation-notes.md`).
> - `verify_invoice_saved` was added later as its own state; see `0008`.
> - Still open, unchanged: verification reads the open editor rather than
>   `Data > Documents` (Task 4.5/5.5) — `TODo.md`'s Open list, item 1.

## Context

Section 5 fills in the three verification stubs
(`order_verification.verify_order_saved`,
`invoice_verification.verify_invoice_matches_order`,
`payment_verification.verify_payment_applied`), each scaffolded to read
live UI state back rather than trust that a save/create action succeeded
(Task Description 4.3-4.5, 5.1-5.3, 5.6). Three things surfaced while
implementing this that shaped the design more than "fill in the stub"
would suggest:

- The scaffold's three functions return `bool` with no way to say *what*
  failed - fine for a single check, not for a step that needs to report
  several independent mismatches (a wrong Cust.Ref. **and** a wrong total
  **and** a missing line) at once.
- Comparing `probes/probe-01-create-order.txt` (an empty New Order editor)
  against `probes/probe-02-fill-create-order.txt` (the same editor,
  filled) - two separate app launches - shows every numeric `auto_id` in
  the editor's field tree differs between the two captures (e.g. the
  Cust.Ref. Edit is `auto_id="132674"` in one, `auto_id="198488"` in the
  other), while each field's accessible name (`Cust.Ref.`, `Total Gross`,
  `Discount`, `VAT`, `Total`) is identical in both. Entity resolution's
  Debtor/Product/VAT/Payment forms were pinned by `auto_id`
  (`entity_resolution/config.py`) on the assumption that a probed
  identifier stays valid; the Order editor disproves that assumption for
  itself specifically.
- No VM probe session has opened Data > Documents, a linked Invoice
  editor, or an Invoice's payment controls (paid checkbox, payment date,
  Value) - only the payment-*method* "Term of Payment" form was probed
  (`probes/probe-10-payment-create-form.txt`). This is a real gap, not an
  oversight: Task 5.2/5.3/5.6 require verifying exactly these fields.

## Decisions

**1. Return `True` or raise one aggregated `ManualReviewRequired`, never a
bare `False`.** All three functions collect every mismatch into a
`problems: list[str]` and raise a single
`ManualReviewRequired(step, "; ".join(problems))` if non-empty, mirroring
`normalization.normalizer.normalize_order`'s aggregate-then-raise shape
(CLAUDE.md's fail-closed principle: manual review should see the whole
picture for one step at once, not just the first problem). The `-> bool`
signature is kept (the functions only ever return `True`) so callers can
still write `if verify_order_saved(...):`, but a caller that wants the
failure detail should catch `ManualReviewRequired` and read `.reason`.
`verify_order_saved` also gained a `normalized_order` parameter beyond its
original scaffold (`order_window` only), since Doc/Design.md's Workflow &
Verification section requires the save step to confirm both persistence
*and* that key fields match the normalized record - one function, one
call, one aggregated result, rather than splitting the two concerns
across separate calls.

**2. Order/Invoice editor fields are selected by accessible name, not
`auto_id` - a deliberate departure from entity_resolution/config.py's
pattern, forced by direct evidence, not preference.** Section 4 pinned
`auto_id`s for the Debtor/Product/VAT/Payment forms and that held up
because those forms are simpler and were captured once each. The Order
editor probe pair (see Context) is the first place in this codebase where
the *same* fields were captured twice, and it falsifies the
"auto_id is stable enough to pin" assumption for those specific fields.
Doc/Design.md's own control-discovery section already ranks accessible
name above `auto_id` ("Accessible name or label... identifies the
intended control"; `auto_id` was only added in Section 4 as a fallback for
blank-named controls) - so this isn't a new rule, it's applying the
existing priority order to a case where it actually matters. The editor's
own tab/pane title doubles as the "was this saved" signal (confirmed:
the same pane is titled `"New Order"` empty, and a real order-number-
shaped string once filled, in the two probe captures) rather than reading
a separate "No." field, since that field is itself blank-named with an
unstable `auto_id` and has no other way to address it reliably.

**3. Unprobed selectors are explicit empty-string placeholders that fail
closed, not a guess.** No VM probe has opened Data > Documents, a linked
Invoice editor, or an Invoice's payment controls. Rather than block all of
Section 5 on a second VM trip (as VAT/Payment briefly were in Section 4)
or guess at field names (ruled out by this project's fail-closed
principle - a wrong guess here is worse than a `NotImplementedError`,
since it could silently target the wrong control), `verification/config.py`
leaves `ORDER_ITEMS_GRID_PANE_AUTO_ID`, `INVOICE_ITEMS_GRID_PANE_AUTO_ID`,
`INVOICE_PAYMENT_METHOD_COMBO_NAME`, `INVOICE_PAID_CHECKBOX_NAME`,
`INVOICE_PAYMENT_DATE_EDIT_NAME`, and `INVOICE_PAYMENT_VALUE_EDIT_NAME` as
`""` with a `# TODO probe` comment. Against a real window, `find_control`
raises `ControlNotFoundError`/`AmbiguousControlError` for these rather
than matching the wrong element - the intended safe state. All three
verification functions are nonetheless implemented in full now (not left
as stubs) and fully unit-tested via duck-typed fakes that give each
placeholder a distinct value for the duration of a test, so the read/
compare/aggregate logic itself is exercised end to end; only the real
identifiers are missing.

**4. `verification/comparisons.py` re-derives locale-tolerant money/percent
parsing rather than importing normalization's.** `normalizer._parse_money`
and its `_normalize_numeric_text` helper are module-private. Rather than
make them public to share across modules, `comparisons.parse_money_text`
is its own small copy of the same cleaning logic - the same choice
`entity_resolution.matching.parse_vat_text` already made for VAT-text
parsing in Section 4, for the same reason: each section owns its own
read-back parsing of UI text, which is a related-but-distinct concern
from parsing raw extraction fields. VAT and discount percentages reuse
`matching.parse_vat_text` directly (no re-derivation needed - it's already
public, and a percentage is a percentage regardless of which field it
comes from).

**5. Order-level and Invoice-level totals are derived once, in one shared
function.** `comparisons.order_level_totals(order)` sums each line's
`recomputed_total` (net) and each line's rounded VAT amount, returning
`(net, vat, gross)`. Both `order_verification` and `invoice_verification`
call this rather than each computing their own copy - the same
"one formula, one place" rule `validators.recompute_line_total` already
follows for the line-total formula, applied here to the order-level
rollup.

## Consequences

- `verification/comparisons.py` and `verification/readback.py` are fully
  unit-tested on macOS: `comparisons.py` is pure (no fakes needed, same
  style as `entity_resolution/matching.py`); the three verification
  functions are tested with duck-typed window/control fakes and a fake
  vision client, the same seam Sections 3/4 established
  (`tests/verification/`).
- The Order editor's `"Total Gross"`-named field is used as the Task
  Description's "Total Net" check (the sum of line net totals) - a
  confirmed, real control, but its exact semantic role was inferred from
  its position among `Total Gross`/`Discount`/`Shipping`/`VAT`/`Total`
  rather than confirmed against a real saved order on the VM. If it turns
  out to mean something else, only `verification/config.py`'s comment and
  `order_verification._field_problems`'s corresponding check need to
  change - the selector itself is real.
- The Invoice editor's field layout (`INVOICE_CUST_REF_EDIT_NAME`,
  `INVOICE_TOTAL_EDIT_NAME`) is *assumed* to match the Order editor's,
  since no linked Invoice editor has been probed independently. This is a
  reasonable assumption (the Invoice is created directly from the Order
  in the same Eclipse RCP application - Task 4.6-4.7) but unconfirmed;
  `Doc/implementation-notes.md` and `TODo.md` flag it as an open item for
  the next VM session, alongside the six placeholder selectors from
  Decision 3. (Both since confirmed live - see the Amendment.)
- Verifying via Data > Documents (Task 4.5/5.5's own prescribed check,
  distinct from reading the editor's internal fields) is not implemented
  in this pass - it would need its own vision-grounded grid read (like
  `entity_resolution.resolver.search_grid_exact`'s pattern) against a pane
  that has never been probed. This is left as a residual for whoever picks
  up the Data > Documents probe, the same way Section 4 left its
  `ComboBox.select(...)` option-string gap for a follow-up VM pass rather
  than blocking on it.
