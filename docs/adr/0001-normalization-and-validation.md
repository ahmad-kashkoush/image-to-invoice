# 0001. Normalization & validation rules (Section 2)

## Status

Accepted

## Context

Section 1 (extraction) produces a `RawOrder`: every field is a loose string
(or `None` if the vision LLM could not read it), plus a per-field
self-reported confidence score. Section 2 must turn this into a typed
`NormalizedOrder` that `entity_resolution` and `ui_automation` can trust
without re-validating, and must do so *before* any UI automation starts -
per `Doc/Design.md`, an incorrect Debtor, price, or VAT rate that reaches
Fakturama's UI would otherwise propagate into a saved financial record.

Several choices here have no single "obviously correct" answer and needed
to be pinned down against the assessment's task description and its
synthetic sample order (`WEB-2026-0714-A17`, Northstar Office GmbH):
ISO dates, EUR, dot-decimal money, prices net, discount as a percentage,
line net totals of 450.00 and 120.00 recomputing to a 570.00 net total.

## Decisions

**1. Line total formula: `quantity x unit_net_price x (1 - discount / 100)`, VAT excluded.**
The task description (rule 3.16) and the sample order's own arithmetic both
confirm discount is a percentage and the line *net* total does not include
VAT. This formula lives in exactly one place
(`validators.recompute_line_total`) and is used both to fill
`NormalizedLineItem.recomputed_total` and to check it against the
extracted `source_line_total`, so the two can never drift apart.

**2. Dates: ISO first, `DD.MM.YYYY` as the only fallback; nothing else is guessed.**
The sample document is ISO (`YYYY-MM-DD`), and the target deployment is a
German-locale Fakturama instance, so `DD.MM.YYYY` is an unambiguous,
worthwhile fallback. A `MM/DD/YYYY`-vs-`DD/MM/YYYY`-style slash date is
*not* accepted, because it cannot be disambiguated without guessing - and a
guessed date is worse than routing to manual review, consistent with the
design's "deterministic rules over guessing" principle.

**3. Money/percent parsing tolerates both dot-decimal and European comma-decimal input.**
The sample order is dot-decimal, but the deployment locale is German, where
source documents may use comma-decimal formatting (`1.234,56`). Both are
normalized to a canonical `Decimal`, with currency symbols and thousands
separators stripped; money is quantized to 2 decimal places, half-up,
matching Fakturama's own money field precision. Percentages are stored as
plain numbers (no `%` sign, not quantized).

**4. `check_confidence` reads `RawOrder`, not `NormalizedOrder` - a scaffolding correction.**
The original stub signature took a `NormalizedOrder`, but confidence data
only exists on the raw extraction models (`RawOrder.confidence`,
`RawAddress.confidence`, `RawLineItem.confidence`), per
`extraction/models.py`'s documented keying convention. `NormalizedOrder`
has nowhere to carry it. `normalizer.normalize_order` has the `RawOrder` in
hand regardless, so this cost nothing to fix before any other code depended
on the wrong signature.

**5. Confidence is checked only on fields the model actually extracted.**
A field the source document never had (e.g. an empty delivery address, no
payment date) has no confidence to be low - it should be judged by
`check_required_fields` (is this field actually required?), not flagged as
an untrustworthy read. Conversely, a field with a non-empty raw value but a
*missing* confidence key is treated as 0.0 (fail closed), per
`extraction/models.py`'s own documented convention - never assumed to be a
confident read just because the model omitted a score.

**6. All failures for an order are aggregated into one `ManualReviewRequired`.**
`normalize_order` collects every parse failure and validator failure before
raising, rather than stopping at the first one. A single malformed field
should not hide a second, unrelated problem on the same order - manual
review should see everything wrong with an order in one pass, not
discover them one fix-and-rerun at a time.

## Consequences

- Normalization is fully testable without Fakturama, a vision model, or
  network access: it is pure functions over dataclasses. The test suite
  uses the sample order's own numbers as a golden fixture, doubling as a
  regression check on the line-total formula.
- The German-locale fallbacks (comma-decimal, `DD.MM.YYYY`) are currently
  unexercised by the sample document; they are deliberate anticipatory
  support for the real deployment locale described in `README.md`, not
  dead code, but should be revisited if a real document ever needs a
  format outside what's covered here (in which case: fail closed and add
  the format, don't guess).
- Because `check_confidence`'s signature changed from the original stub,
  any future code written against the old `(NormalizedOrder, threshold)`
  shape (there was none yet) would need updating - noted here so it isn't
  rediscovered as a surprise.
