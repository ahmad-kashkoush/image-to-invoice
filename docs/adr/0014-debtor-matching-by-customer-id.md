# 0014. Debtor matching: all five task-2.3 fields, plus a real Customer ID

## Status

Accepted

## Context

Task 2.3 (this is section 2's picker; the analogous rule for `resolve_debtor`
is implied by the same standard applied elsewhere in the task description):
treat a Debtor as an exact match only when the visible Company, First Name,
Name, ZIP, and City all match the extracted values. `entity_resolution/
debtor.py::resolve_debtor` did not follow this - it searched the Debtors grid
by Company only (`screens.DEBTORS_SEARCH_COLUMNS = ["Company Name"]`) and
`matching.exact_text_matches` did a strict `==` against that one column,
never checking the other four. `README.md`'s Next Steps already named this
gap.

Separately, a live run reproduced a duplicate-Debtor bug: running the
orchestrator twice with the same Debtor created a second record instead of
matching the first. `docs/implementation-notes.md` already documents that
this app's grid **Company** column can render visually clipped for a long
name - confirmed live for the *"Select the address"* picker (a real
"Northstar Office GmbH" row read back as "thstar Office ..."). The working
hypothesis going in was that `resolve_debtor`'s own Company-only strict-equality
search hit the same clipping, explaining both the task-2.3 gap and the
duplicate in one root cause.

**Live VM check (2026-09-14) partially confirmed, partially falsified this:**
- The Debtors list grid's real columns are `No., First Name, Name, Company,
  ZIP, City` - the same six columns as the picker's own grid
  (`ORDER_SELECT_ADDRESS_SEARCH_COLUMNS`), not the single `"Company Name"`
  column the code assumed.
- Company did **not** render clipped in this grid for the long name that had
  previously triggered a duplicate. The clipping hypothesis, confirmed for
  the picker dialog, does not hold for the Debtors list grid `resolve_debtor`
  actually searches - a different widget. The precise mechanism behind the
  original duplicate-creation run was not re-isolated; it is not claimed to
  be understood, only that Company-column clipping in this grid is ruled
  out as the cause.
- The New Debtor form's Customer ID field has a real accessible name
  ("Customer ID"), confirmed in `probes/probe-04-fill-create-debitor.txt`
  (`child_window(title="Customer ID", auto_id="133128", control_type="Edit")`).
  It is not one of this app's blank-named, session-unstable-`auto_id`
  controls, so it can be read back by name like every other named field in
  this codebase, and the existing `DEBTOR_FORM_CUSTOMER_ID_AUTO_ID` constant
  (unused, no caller ever read it) is unnecessary.

Regardless of the duplicate's exact mechanism, the pre-existing Company-only
match was still non-compliant with task 2.3's five-field rule on its own
terms, and `entity_resolution/models.py::ResolvedEntity.identity` was always
fabricated from the search key (`company_name`) rather than read off any
actual row or saved record - true for both the search and create branches of
`resolve_debtor`.

## Decisions

**1. Match on all five fields task 2.3 names (Company, First Name, Name, ZIP,
City), not four.** With no live evidence that any of these five columns clip
in the Debtors list grid, there is no reason to drop Company from the
comparison the way the picker's own workaround does - that workaround exists
specifically because the picker's grid *was* confirmed to clip Company. Full
five-field exact matching is closer to the letter of task 2.3 and is
implemented as a new `matching.exact_debtor_matches`, alongside
`exact_text_matches`/`exact_vat_matches`, following the same shape (a row
missing a compared column is excluded, not raised).

**2. Return the row's real "No." (Customer ID) as `ResolvedEntity.identity`,
for both branches.** Task 2.3 itself doesn't ask for this - it only asks
Fakturama to select the matched row - but `ResolvedEntity` is part of this
codebase's own contract and was returning a value (`company_name`) that was
never actually read off anything: not the matched grid row, not the created
record. `search_by()` now reads the matched row's `"No."` cell; `create()`
reads the New Debtor form's own "Customer ID" field by name
(`readers.read_field_text`, the same read-back primitive
`verify_saved_fields` already uses) after Save, rather than by its
unconfirmed, unused auto_id. `DEBTOR_FORM_CUSTOMER_ID_AUTO_ID` is replaced
with `DEBTOR_CUSTOMER_ID_EDIT_NAME = "Customer ID"`.

**3. The search key stays the Company name; only the match decision and the
returned identity change.** Fakturama's own "Search:" filter still narrows
candidate rows by company name before any field-level comparison runs - the
Customer ID isn't known from the order image, so it can never be a search
input. This is unchanged from before this ADR.

**4. `resolver.resolve_exact_or_create`'s 0/1/many counting is unchanged.**
The fix is entirely in what `search_by()` counts as a match; the caller
(`orchestrator/steps/order_editor.py::populate_order_fields`) already
discards the returned `ResolvedEntity`, so no downstream wiring changes.

## Consequences

- `entity_resolution/debtor.py::resolve_debtor` now splits
  `order.contact_name` via the same `partition(" ")` idiom `_create_debtor`
  already uses, so a created record and a later match against it agree on
  what counts as First/Last Name (including the same pre-existing quirk:
  a middle name lands in "Name"/Last Name, not dropped).
- The "Select the address" picker (`orchestrator/steps/pickers.py`) has its
  own, separately-coded search-and-pick logic with the same
  confirmed-for-that-dialog Company-clipping problem, worked around there
  by requiring exactly one row rather than field equality. It is unchanged
  by this ADR; `TODo.md` now notes it as a candidate to match on Customer ID
  too, now that `resolve_debtor` exposes one reliably.
- If a future, longer company name is found to clip in the Debtors list grid
  after all, `exact_debtor_matches`'s Company comparison would need the same
  kind of fallback the picker already uses (drop Company, trust the other
  four, or require exactly one row) - not assumed impossible by this ADR,
  just unobserved in the live check that motivated it.
