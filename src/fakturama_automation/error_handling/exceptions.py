from __future__ import annotations


class ManualReviewRequired(Exception):
    # Deliberately carries only step/reason - manual_review.py forwards a
    # `details` attribute via getattr if a caller sets one, so richer partial
    # state can be added later without a signature change.

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"{step}: {reason}")
