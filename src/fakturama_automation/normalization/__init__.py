"""Normalization package.

Converts raw extraction output into the typed, validated form Fakturama's
UI expects, and recomputes line totals to catch bad extractions before any
automation starts. See section 2 of the project plan.

`normalizer.normalize_order` is the single entry point orchestrator should
call; it raises `error_handling.exceptions.ManualReviewRequired` rather than
returning a partially-trustworthy order.
"""
