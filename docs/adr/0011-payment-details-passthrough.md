# 0011. `payment_details` is carried through as optional free text, not validated

## Status

Accepted (amends 0001)

## Context

`RawOrder.payment_details` (IBAN/BIC or other payment free text, extraction's
own field, `extraction/models.py:59`) was captured by extraction but silently
dropped at the extraction → normalization boundary: `NormalizedOrder` had no
corresponding field and `normalize_order` never read it. Per this project's
fail-closed principle, a dropped field is worse than an unvalidated one - it
means nothing downstream can ever notice a missing or garbled bank reference,
because nothing downstream ever sees it. Fixing the drop raised two questions
the design doc doesn't answer directly.

## Decisions

**1. A missing `payment_details` passes through as `""`; it does not raise
`ManualReviewRequired`.** Whether a bank reference is expected depends on
`payment_method` (a bank transfer plausibly has one; cash or an
already-settled invoice plausibly doesn't), and this project's entity
resolution is exact-match only, never fuzzy (see ADR 0003) - classifying
"this payment method requires bank details" from free text would be exactly
that kind of fuzzy judgment call. Decisive evidence against making it
required: the project's own golden sample order (`WEB-2026-0714-A17`,
`tests/normalization/test_normalizer.py`) is `payment_method="Bank Transfer"`,
`payment_status="PAID"`, and still has `payment_details=None`. A "required for
transfers" rule would route the reference order to manual review.

**2. No IBAN/BIC format or checksum validation.** Extraction's own schema
defines the field as free text - `"IBAN/BIC or other payment detail free
text"` (`extraction/vision_extractor.py:86`) - specifically so it is not
constrained to one bank-detail format. A mod-97 IBAN checksum or BIC pattern
check would reject legitimate non-IBAN entries the schema explicitly permits,
and nothing downstream parses the value as a structured bank identifier -
there is no payoff to buy back the false-failure risk.

**3. Low confidence on a *present* value already fails closed - no new code
needed.** `payment_details` was already listed in
`ORDER_LEVEL_CONFIDENCE_FIELDS` (`extraction/models.py:20`) before this fix,
so `validators.check_confidence` already treats a present-but-low-confidence
`payment_details` as a shortfall, same as any other order-level field. The
fix only adds the missing pass-through (`normalizer.py`:
`payment_details=_trim(raw_order.payment_details)`); the confidence gate
needed a regression test, not a change.

**4. Surfaced in the `--dry-run` summary, not otherwise checked.**
`orchestrator/__main__.py::_summarize` prints `payment_details` when present,
so a human reviewing a dry run can notice an unexpected absence or garbled
value without the pipeline hard-stopping on it.

## Consequences

- `NormalizedOrder.payment_details` exists and is populated whenever
  extraction reads one; the golden sample and any order without one continue
  to normalize cleanly with `payment_details == ""`.
- No new failure mode was added to `normalize_order`; the aggregated-failures
  contract (ADR 0001, decision 6) is unchanged.
- **Nothing writes `payment_details` into Fakturama, and a live-VM check
  (2026-09-12) confirmed there is nowhere to write it to.** The Debtor
  editor's only other tab (`Miscellaneous`) has no bank/IBAN field - Web
  Site, Supplier Number, Corporate ID number, Alias name, VAT Number,
  Reliability, Net or Gross, GLN, WebShop user name, Birthday, the
  already-wired Payment combo, and Discount, and nothing else. The Payment
  Method editor (the "Bank Transfer" record `payment_method.py` creates) has
  an `Account` field, but it is a standalone combo with no visible list of
  bank accounts anywhere in the app's navigation - not a place this
  pipeline can attach a value to either. `payment_details` is therefore
  genuinely a source-document-only field: captured for completeness (it is
  presumably the seller's own bank info as printed on the order/invoice the
  customer received, not a Debtor attribute), with no Fakturama UI
  counterpart to write to or verify against. No further UI wiring is
  planned; the `TODo.md` Open item this ADR originally added has been
  removed rather than left open, since there is nothing left to probe.
