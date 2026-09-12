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
- Nothing writes `payment_details` into Fakturama or verifies it there -
  `ui_automation/locators.py::payment_details_pane` currently only yields the
  payment-method combo and date row, and it is unconfirmed whether an
  IBAN/BIC belongs on the Debtor record or the Invoice in Fakturama. That is
  tracked as a new `TODo.md` Open item, not solved here - it needs a live-VM
  probe before a write/read-back can be designed, the same prerequisite as
  the other unwired fields (Order Date, currency, addresses).
