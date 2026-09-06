"""Exceptions that route the workflow to manual review.

Any ambiguous match (entity_resolution) or failed verification
(verification) anywhere in the workflow should ultimately surface as one of
these, caught in one place by manual_review.py rather than handled ad hoc
at each call site.
"""

from __future__ import annotations


class ManualReviewRequired(Exception):
    """Raised when the workflow cannot safely proceed and must stop for a
    human to look at it.

    Deliberately carries only step/reason for now - manual_review.py
    forwards a `details` attribute via getattr if a future caller sets one,
    so richer partial state can be added later without a signature change.
    """

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"{step}: {reason}")
