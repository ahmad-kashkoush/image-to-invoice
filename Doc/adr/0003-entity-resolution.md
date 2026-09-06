# 0003. Entity resolution: vision-grounded grids, ResolvedEntity, and a probe-driven build order (Section 4)

## Status

Accepted

## Context

Section 4 turns a required Debtor, Product, VAT rate, or Payment Method
into a Fakturama record: search for an exact match, create only if none
exists, and raise for manual review if the search is ambiguous. Before
writing any of it, the four entity screens were probed on the Windows 11
ARM VM (`probes/probe-*.txt`) per the project's build order, and the
results reshaped the design more than a normal "pin the control names"
pass would:

- Each entity's **search box and create form are driveable via UIA**, with
  stable `auto_id`s - but most of these controls (search boxes, several
  name/address fields) carry **no accessible name at all**, so they can
  only be found by `auto_id`, which `ui_automation.controls.find_control`
  did not support (it only matched on `control_type`/`name`).
- Each entity's **results grid is invisible to UIA.** `probes/probe-06-debitors.txt`,
  `probe-07-products.txt`, and `probe-09-Payment.txt` all show the results
  pane as an empty `Pane` - no `DataItem`/`ListItem` rows, no readable cell
  text. Fakturama's list views are custom-rendered (SWT/NatTable) grids
  that simply do not expose their rows to Windows UI Automation. This is
  the load-bearing fact: the scaffold's `search_by: Callable[[], list[Any]]`
  assumed rows could be read and counted through
  `ui_automation.controls.find_all_controls` the same way every other
  Section 3 lookup works, and they cannot.
- Two create forms (VAT, Payment) were not captured cleanly - a stale
  Product editor was left open during those probe passes, so their
  create-form field `auto_id`s are still unknown.

`Doc/Design.md`'s own control-discovery section already sanctions a
fallback for exactly this situation ("OCR or visual inspection can
disambiguate a control when UIA metadata is insufficient... for example, a
custom-rendered element"), so this wasn't a question of whether to add a
fallback, but how to shape it and how much of Section 4 to build now versus
after a second probe pass.

## Decisions

**1. Vision/OCR grounding for the read half, not the data store and not a
blind keyboard-select.** Three approaches were considered for reading grid
state: (a) screenshot the filtered grid and read it with a vision pass,
(b) query Fakturama's underlying data store directly, (c) filter by the
exact key, blindly select the first row via keyboard, and trust that exact
keys are unique. (a) was chosen: it stays UI-driven (this is a UI
automation project, not a database-migration one), it reuses the
already-built injectable vision-client pattern from
`extraction/vision_extractor.py` rather than inventing a new integration
point, and unlike (c) it still lets the system *count* matches (0/1/>1)
rather than assuming uniqueness - preserving the fail-closed ambiguity
check the design requires. The cost is an extra vision call per search;
accepted, matching the project's existing cost/correctness tradeoff
(Haiku 4.5 chosen for extraction on the same basis).

**2. A short fixed settle delay before each grid screenshot, not a poll.**
`ui_automation.waits` avoids fixed sleeps everywhere else, polling for a
UIA-visible signal instead. There is no such signal here - the grid's
UIA-invisibility is exactly the problem - so polling would mean firing a
vision API call on every poll instead of once. `resolver.search_grid_exact`
uses one short, configurable settle delay (`entity_resolution/config.py`'s
`SEARCH_SETTLE_SECONDS`) followed by a single screenshot and read. This is
a deliberate, documented exception to the "poll, don't sleep" rule, not an
oversight.

**3. `controls.find_control`/`find_all_controls` gained an `auto_id`
parameter.** Rather than bypass Section 3's discovery layer and call
`parent.child_window(auto_id=...)` directly from `entity_resolution`
(which would lose `find_control`'s bounded-retry and ambiguity-detection
behavior, and split control discovery across two mechanisms), `auto_id`
was added as a third optional filter alongside `control_type`/`name`,
passed straight through to `parent.children()`. This is additive and
backward compatible - existing calls that don't pass `auto_id` are
unaffected (verified: all of Section 3's existing tests still pass
unchanged) - and keeps every entity resolver going through the same
discovery/retry/ambiguity path as the rest of the codebase.

**4. `ResolvedEntity` (identity, `created`, `element`) instead of the
scaffold's bare `Any` return.** The original scaffold typed every
resolver's return as `Any` with a comment that it "should be whatever
identifies a Fakturama record to later ui_automation steps." A named
dataclass was introduced instead because `created` (matched an existing
record vs. just made a new one) is state Verification and the
manual-review log both need, and there was no way to recover it from a
bare value - `resolve_exact_or_create`'s zero/one/many branches would
otherwise return heterogeneous, indistinguishable shapes. Concretely, each
resolver's `search_by`/`create` callbacks both return `ResolvedEntity`
directly (`created=False`/`created=True` respectively), so
`resolve_exact_or_create` didn't need its own signature changed to smuggle
this through - it stays a generic, reusable zero/one/many decision over
whatever type the caller's callbacks agree on.

**5. `resolve_exact_or_create` gained keyword-only `entity`/`step`
parameters (backward compatible).** The scaffold's version took only
`search_by`/`create`. Manual review needs to know *which* debtor or SKU
was ambiguous, not just a bare match count, so `entity`/`step` (both
optional, defaulting to generic text) are threaded into the
`ManualReviewRequired` reason. Existing call shape is unaffected.

**6. Debtor and Product were implemented in full; VAT rate and Payment
Method were not - a probe gap, not a scope cut.** Debtor
(`probes/probe-06-debitors.txt`, `probe-03/04-*-debitor.txt`) and Product
(`probes/probe-07-products.txt`) captured every control needed end to end.
VAT's list view never rendered during its probe pass (a stale Product
editor was open instead), and Payment's create form was never opened, so
neither has known create-form `auto_id`s. Rather than block all of Section
4 on a second VM trip, or guess at field names (which this project's
fail-closed principle rules out), `payment_method.py` implements its fully
probed search half and raises a specific, named error from `create()`;
`vat_rate.py` is left as a stub with a docstring pointing at exactly what
still needs probing. `product.resolve_product`'s `create()` path calls
`vat_rate.resolve_vat_rate` first (per the original scaffold's "not
skipped" instruction), so creating a genuinely new product is also blocked
until that gap closes - this is intentional: a partially-working VAT
creation path would be worse than a clearly blocked one.

**7. Case-sensitive exact string match, and numeric (not string) VAT
comparison.** `entity_resolution/matching.py`'s `exact_text_matches` does
plain `==` on already-normalization-trimmed text - no case-folding, no
partial match - so a near-miss (different casing, extra punctuation) is
never silently treated as the same record; it falls through to creation or
ambiguity instead, per the design's "exact match only, never fuzzy"
principle. `exact_vat_matches` parses each row's VAT text as a `Decimal`
(reusing `normalization.normalizer`'s locale-tolerant number parsing
approach) and compares numerically, so `"19"`, `"19.00"`, and `"19,00 %"`
all match a target of `Decimal("19")` - VAT rates are a numeric quantity a
document could render several equivalent ways, unlike a name or SKU, which
should match verbatim.

## Consequences

- `entity_resolution/resolver.py`, `matching.py`, and `models.py`, plus
  `ui_automation/vision_grounding.py`, are fully unit-tested on macOS with
  duck-typed fakes and a fake vision client - no real window, no
  screenshot, no network - the same seam `ui_automation.controls`/`waits`
  already established (ADR 0002). `debtor.py` and `product.py` are also
  fully unit-tested this way, exercising their whole search/match/create
  sequence against a fake control registry.
- The vision-grounding fallback is not unique to Section 4: the same
  UIA-opacity was found in the Order editor's line grid, customer field,
  and payment control while probing (`probes/probe-01/02-*.txt`), and will
  affect Section 5 (Verification, which reads state back the same way) and
  the orchestrator's order-line entry. `ui_automation/vision_grounding.py`
  was placed in `ui_automation`, not `entity_resolution`, specifically so
  those sections can reuse it rather than reinventing it.
- `vat_rate.resolve_vat_rate` remains `NotImplementedError`, and
  `product.resolve_product`'s create path is blocked transitively until it
  is implemented. `payment_method.resolve_payment_method`'s create path
  raises a specific `RuntimeError` rather than `NotImplementedError`,
  since its search half *is* real - only creation is blocked. Both name the
  exact gap in their own error message, so the next probe session knows
  what to capture.
- `ComboBox.select(...)` calls in `debtor.py` (Country) and `product.py`
  (VAT) use option-string guesses (e.g. `f"{item.vat_percent}%"`) that were
  never verified against Fakturama's actual dropdown contents - the combos
  were closed when probed. These are left to raise naturally if the guess
  doesn't match a real option, rather than being caught and silently
  skipped, consistent with this project's fail-closed principle; the
  correct fix is enumerating each combo's real options on the next VM
  pass, not adding a try/except here.
