# 0010. Refactoring P1: one parser, a real LLM boundary, and verified creation

## Status

Accepted (2026-09-06). Verified by a differential check against the code it
replaced, a new pure test, an import sweep and both CLI paths; **not yet
re-verified by a live VM run** — see Consequences.

Follows `0009`, which took the P0 items from the same plan
(`.claude/plans/refactoring-architecture-review.md`). Amends `0003`
(Decision 4's `ResolvedEntity`, Decision 7's VAT parsing) and `0004`
(Decision 4's deliberate parser duplication).

## Context

`0009` left two of the four bad dependency edges in place and named them as
the next sub-plan: `verification` importing `entity_resolution` for a
parsing helper, and `normalization` importing the module that calls the
Anthropic API. It also left `ResolvedEntity` built and discarded by every
caller, master-data creation as the one mutation class with no verification,
and `grid_geometry` — the most subtle pure code in the repo — untested.

## Decisions

**1. One parsing module, three compositions.**
`normalization/parsing.py` holds the primitives: strip currency symbols,
strip spaces, normalise decimal separators, parse a Decimal, parse a
percent out of UI text, parse a date against a supplied format list. The
separator rule existed in three near-identical copies.

What is deliberately *not* unified is what each caller composes from them.
Raw document text, UI-rendered text and a dropdown label have different
input spaces, and merging them would loosen parsing:

- `normalize_decimal_separators` does not strip whitespace. Folding the
  strip in — as two of the three copies did — would make `"1 9"` parse as
  19 in the third, which reads dropdown text.
- The normalizer keeps its own percent path. `parse_percent_text` searches
  for `<number>%` anywhere, which is right for a dropdown label
  (`"VAT 19 (19%)"`) and wrong for a document field, where `"abc 19%"` is a
  misread rather than a percentage.
- The date formats stay per-caller. The normalizer accepts ISO and an
  unambiguous day-first fallback; verification also accepts the month-name
  forms Fakturama's widgets render. `0004` Decision 4 justified duplicating
  the *parsers* to preserve that distinction; the distinction is real, but
  it lives in the format list, not in three copies of the separator rule.

This was checked rather than assumed: a differential harness reimplemented
all three original functions verbatim and compared them against the new
compositions over 40 inputs — 160 comparisons, zero differences.

`matching.parse_vat_text` is deleted rather than kept as an alias; one name
for one thing. With it goes `verification`'s import of
`entity_resolution`.

**2. The LLM boundary is enforced at the package's front door, not just in
one module.** Moving the confidence field lists from `vision_extractor.py`
to `extraction/models.py` was necessary but not sufficient: importing
`extraction.models` still runs `extraction/__init__.py`, which imported the
vision adapter, which imports `anthropic`. So `extract_order` now imports
its two implementation modules inside the function.

Same reasoning as the deferred pywinauto import in `state_machine`
(`0007` Decision 4): an adapter's heavy dependency should load when the
adapter is *called*, not when something merely names its data shapes.
Confirmed by blocking `anthropic` through `sys.meta_path` and importing and
using the whole normalization and comparison layer.

**3. Master-data creation is verified, by reading the saved form back.**
`resolver.verify_saved_fields` re-finds the identifying controls by name
after the Save click and fails closed on a mismatch: Company for a Debtor,
Item Number for a Product, Name for a payment method, and Name *and Value*
for a VAT rate.

This is the mutation class the project's own worst bug lived in.
`_create_vat_rate` silently saved Value as `0%` for every rate because that
field arrives pre-filled and was typed into rather than replaced; the
resolver could then never find its own record, so every run created another
duplicate, and the catalog degraded until the product picker misbehaved.
The visible symptom — an order line added three times — was several layers
from the cause.

Controls are re-found by name rather than reusing the references the create
form filled: a save can rebuild the widget tree, and a stale wrapper reads a
value no longer on screen. That a saved record's editor stays open and
readable is not an assumption — it is how the Company persistence bug was
isolated in the first place (`0007` Decision 7).

Value is compared numerically, not as text: Fakturama re-renders what was
typed into these fields, so the text coming back is not necessarily the text
that went in.

The stronger alternative — re-searching the list for the new record, as Task
2.12/3.12 prescribe — is not done. It costs another navigation and vision
call per creation, and reading the form back catches the failure this
system has actually had. Noted as the upgrade if the form read-back proves
insufficient.

**4. Combo selection is verified with the predicate that chose it.**
Clicking a coordinate derived from a screenshot assumes those pixels map 1:1
to screen coordinates, which is false under DPI scaling — and a mis-scaled
click lands somewhere harmless and leaves the combo on its previous value
with nothing raised. `TODo.md` described this as failing closed; it did not
fail at all at the point of action, only indirectly and much later.

`_click_and_confirm` reads the combo back and applies the *same* callable
that selected the option, so the check means "the combo now holds something
satisfying what was asked for" rather than assuming the widget echoes the
dropdown row verbatim. This was the last mutation in the codebase without an
act/verify pair.

**5. `ResolvedEntity` is connected, not deleted.** The plan allowed either,
preferring connection. Full connection — matching a Debtor by Customer ID
instead of by the clipped Company column — still needs a probe of the
Debtors list for a No. column that no probe session has captured, so that
remains open. But `created` has a real consumer now: the run log says
whether each Debtor, Product, VAT rate and payment method was *matched* or
*created*, which is exactly the distinction `0003` Decision 4 said the log
would need. `element` is dropped — nothing ever read it, and with Decision 3
each create half verifies its own record locally rather than handing a
reference upward. The dataclass is frozen.

`resolve_exact_or_create` is typed to `ResolvedEntity` rather than staying
generic, since all four callers always used it and the logging now depends
on it.

**6. `--dry-run`, and a run that says what it is doing.** A run drives a
desktop application for minutes and previously produced no output at all
until it was over. `logging` at INFO now names each state entered, each
resolver decision, and the outcome; `--quiet` reduces it to the outcome.

`--dry-run` runs EXTRACT and NORMALIZE and prints the record — the whole
pipeline up to the point Fakturama is needed. It makes every change to
extraction or normalization checkable in a second, on any machine, and it is
what turned "the parser merge preserves behaviour" from a claim into
something observable end to end.

`WorkflowState.EXTRACT`/`NORMALIZE` were renamed to `"extraction"` and
`"normalization"` so a queue entry and the CLI's own "stopped at" line
always agree; every other state value already matched the step its module
raises under.

**7. `grid_geometry` gets a test, with a stated limit.** It is pure, it is
the most subtle deterministic code here, and it sits on the path that writes
quantities into an accounting document.

The fixture is *synthetic* — a grid drawn to the structure the algorithm
expects — because capturing a real Fakturama grid needs the VM. That pins
the contract (column bounds, the row lattice, the scroll and clipping
rejections) and it has teeth: five of the six tuned constants, when
perturbed, break at least one test, including `_LINE_THRESHOLD` pinned from
both sides. It does not prove agreement with how Fakturama actually renders.
Replacing the drawn fixture with a committed real screenshot is the stronger
version and is worth doing on the next VM session; the assertions carry over.

**8. Reading a control back moved to `ui_automation.readers`.** Reading is
not a verification concern — entity resolution reads a record it just saved,
and the payment step reads the combo it just set. `verification/readback.py`
is gone; `verification/config.py` with it, both of its constants having been
dead or relocated.

## Consequences

- **All four bad dependency edges from the original analysis are closed.**
  `ui_automation` imports nothing from this project; `verification` and
  `entity_resolution` are peers that do not import each other;
  `normalization` reaches only `extraction.models`, without the SDK behind
  it.
- **Three new ways to fail closed.** A Debtor/Product/VAT/payment-method
  record that does not save correctly, and a combo selection that does not
  take, now stop the run instead of surfacing later or not at all. That is
  the intent, and it means the first live run after this change can stop
  where it previously continued — on the golden order that must be
  reproduced and explained, not worked around.
- **Decision 4 is the highest-risk item here.** If Fakturama's combo renders
  its selected value in a form the selecting predicate does not accept, every
  product creation fails closed. The predicate was chosen over text equality
  precisely to tolerate re-rendering, but it is unverified against a live
  widget. If it misfires, the fix is to widen the comparison, not to remove
  the check.
- **Not yet verified live.** Everything here was checked by a differential
  parser harness, the new geometry test, a full import sweep, an
  SDK-blocked import of the domain layer, and both CLI paths end to end.
  None of that touches a real Fakturama window.
- Still open from the plan and unaddressed here: matching the Debtor by
  Customer ID (needs a probe), currency absent from the domain model,
  `order_date` never written, and verification reading the open editor
  rather than `Data > Documents`.
- `waits.wait_for_dialog` and `wait_for_stable_row_count` still have no
  production caller. Left alone deliberately — removing them also removes
  `tests/ui_automation/test_waits.py`'s reason to exist, which is a
  deliberate deletion rather than a tidy-up.
