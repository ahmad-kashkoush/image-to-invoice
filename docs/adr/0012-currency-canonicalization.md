# 0012. Currency capture and canonicalization

## Status

Accepted (amends 0001)

## Context

`currency` was absent everywhere - from `RawOrder`, `NormalizedOrder`, and
the extraction schema - despite `README.md`'s Next Steps already flagging it
as a real gap: both parsers strip currency symbols before comparing, so a
`$` total would verify clean against a EUR order. Adding the field raised
the same question this repo already answered for dates (ADR 0001, decision
2) and will answer again for `normalize_decimal_separators` (see
`docs/implementation-notes.md`'s Fix D entry): when raw input is genuinely
ambiguous, do not guess - fail closed to manual review.

Currency symbols are not all equally ambiguous. `€` and `£` each name
exactly one currency in any real-world usage this system will encounter.
`$` and `¥`, by contrast, are shared by several currencies (USD, CAD, AUD,
HKD, SGD, ... for `$`; JPY and CNY for `¥`) - a document showing a bare `$`
gives no way to know which one without external context (e.g. the debtor's
country), and this repo's entity resolution is exact-match-only precisely to
avoid that kind of inference (`CLAUDE.md`).

## Decisions

**1. Symbols/words that name exactly one currency map to their ISO 4217
code; symbols shared by multiple currencies fail closed.**
`normalization/parsing.py::canonicalize_currency` recognizes:
- Unambiguous symbols: `€` -> `EUR`, `£` -> `GBP`.
- Unambiguous words: `EURO(S)` -> `EUR`, `POUND(S)`/`STERLING` -> `GBP`.
- Any spelled-out ISO 4217 code (`EUR`, `GBP`, `USD`, `CHF`, `JPY`, `CNY`,
  `CAD`, `AUD`, `NZD`, `SEK`, `NOK`, `DKK`, `PLN`, `CZK`, `HUF`) - the code
  itself is precise even though `$`/`¥` alone are not, so spelling one out
  is never ambiguous.
- Ambiguous symbols (`$`, `¥`) and anything unrecognized return `None`.

**2. `None` from `canonicalize_currency` is a normalization failure, not a
silent default.** `normalizer._canonicalize_currency` appends to the
existing aggregated `failures` list (`currency: ambiguous or unrecognized
currency '<text>'`) and routes to `ManualReviewRequired`, the same shape as
every other check in `normalize_order` - never guessing which of several
currencies a bare `$` means.

**3. A missing currency (not printed on the document) stays optional, not a
failure.** Mirrors the `payment_details` precedent (ADR 0011): absence is a
different case from an unreadable-but-present value. `raw_order.currency is
None` normalizes to `""` with no failure; `check_confidence` already covers
the present-but-low-confidence case via `ORDER_LEVEL_CONFIDENCE_FIELDS`
(`extraction/models.py`), which now includes `"currency"`.

**4. Extraction captures currency as printed, not inferred.** The vision
prompt (`vision_extractor.py::_EXTRACTION_PROMPT`) explicitly tells the model
not to infer currency from the debtor's address or language - only from
what is visibly printed on the document, consistent with this module's
"never guess" rule applying at the extraction boundary too.

## Consequences

- Currency now flows end-to-end: `RawOrder.currency` (extraction) ->
  `NormalizedOrder.currency` (an ISO 4217 code or `""`), and is
  confidence-gated like every other order-level field.
- The symbol/word lists in `parsing.py` are not exhaustive of ISO 4217 - only
  the currencies plausible for this deployment's target market (the
  German-locale Fakturama instance, per `README.md`) and its immediate
  neighbors are covered. A real document in an uncovered currency fails
  closed to manual review rather than guessing; extending the map is a
  low-risk, purely additive change if that happens.
- **UI-side verification remains open** (`TODo.md`): nothing yet compares
  `NormalizedOrder.currency` against a Fakturama order-editor control. That
  needs a live-VM probe first to confirm whether Fakturama's order editor
  exposes currency as a per-order field at all, or as a fixed
  per-installation setting - which decides whether a `currency_equals`
  comparator in `verification/comparisons.py` is even meaningful.
